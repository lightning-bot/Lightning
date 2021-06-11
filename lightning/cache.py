"""
Lightning.py - A personal Discord bot
Copyright (C) 2019-2021 LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# _wrap_new_coroutine, _wrap_and_store_coroutine, ExpiringCache is provided by Rapptz under the MIT License
# Copyright ©︎ 2015 Rapptz
# https://github.com/Rapptz/RoboDanny/blob/19e9dd927a18bdf021e4d1abb012ae2daf392bc2/cogs/utils/cache.py
import asyncio
import enum
import inspect
import time
from functools import wraps
from typing import Any, Union

from aredis import StrictRedis
from lru import LRU

from lightning.config import CONFIG


class CacheError(Exception):
    pass


def _wrap_and_store_coroutine(cache, key, coro):
    async def func():
        value = await coro
        cache[key] = value
        return value
    return func()


def _wrap_new_coroutine(value):
    async def new_coroutine():
        return value
    return new_coroutine()


class ExpiringCache(dict):
    def __init__(self, seconds):
        self.__ttl = seconds
        super().__init__()

    def __verify_cache_integrity(self):
        # Have to do this in two steps...
        current_time = time.monotonic()
        to_remove = [k for (k, (v, t)) in self.items() if current_time > (t + self.__ttl)]
        for k in to_remove:
            del self[k]

    def __getitem__(self, key):
        self.__verify_cache_integrity()
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        super().__setitem__(key, (value, time.monotonic()))


class BaseCache:
    """Base cache strategy class"""

    def __init__(self, name: str):
        self.name = name
        # I kinda don't like this but whatever.
        registry.register(name, self)

    async def _get(self, key):
        raise NotImplementedError

    async def get(self, key):
        """Gets a key from cache"""
        return await self._get(key)

    async def get_or_default(self, key, *, default=None):
        """Gets a key from cache.

        If the key is not cached, returns the default.
        """
        value = await self._get(key)
        return value if value is not None else default

    async def _set(self, key, value):
        raise NotImplementedError

    async def set(self, key, value):
        """Sets a key into cache"""
        await self._set(key, value)

    async def _invalidate(self, key):
        raise NotImplementedError

    async def invalidate(self, key):
        """Invalidates a key from cache"""
        await self._invalidate(key)

    async def _clear(self):
        raise NotImplementedError

    async def clear(self):
        """Clears the cache"""
        await self._clear()


class DictBasedCache(BaseCache):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def _get(self, key):
        return self._cache[key]

    async def _set(self, key, value) -> None:
        self._cache[key] = value

    async def get_or_default(self, key, *, default=None):
        try:
            value = await self._get(key)
        except KeyError:
            value = default

        return value

    async def _invalidate(self, key) -> bool:
        try:
            del self._cache[key]
            return True
        except KeyError:
            return False

    async def _clear(self) -> bool:
        self._cache.clear()
        return True


class RawCache(DictBasedCache):
    _cache = {}


class LRUCache(DictBasedCache):
    def __init__(self, *args, max_size=128, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = LRU(max_size)

    @property
    def stats(self):
        return self._cache.get_stats()


class TimedCache(DictBasedCache):
    def __init__(self, *args, seconds, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = ExpiringCache(seconds)


class RedisCache(BaseCache):
    def __init__(self, **kwargs):
        self.pool = start_redis_client()
        super().__init__(**kwargs)

    async def _get(self, key):
        return await self.pool.get(key)

    async def _set(self, key, value):
        return await self.pool.set(key, value)

    async def _clear(self):
        """Clears all keys stored in the current redis database."""
        return await self.pool.flushdb()


class Strategy(enum.Enum):
    raw = 1, RawCache
    lru = 2, LRUCache
    timed = 3, TimedCache
    redis = 4, RedisCache


def key_builder(args, kwargs, *, ignore_kwargs=False) -> str:
    key = []
    # I don't care about self and need an easy way to invalidate
    key.extend(repr(o) for o in args if o.__class__.__repr__ is not object.__repr__)

    if not ignore_kwargs:
        for k, v in kwargs.items():
            if k == 'connection' or k == 'conn':
                continue

            key.append(repr(k))
            key.append(repr(v))

    return ':'.join(key)


class cached:
    def __init__(self, name, strategy=Strategy.raw, *, rename_to_func=False, ignore_kwargs=False, **kwargs):
        self.rename_to_func = rename_to_func
        self.ignore_kwargs = ignore_kwargs
        self.key_builder = key_builder

        self.cache = strategy.value[1](name, **kwargs)

    def __call__(self, func):
        if self.rename_to_func is True:
            registry.rename(self.cache.name, f'{func.__module__}.{func.__name__}')

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.decorator(func, *args, **kwargs)

        async def _invalidate(*args, **kwargs):
            return await self.cache.invalidate(self.key_builder(args, kwargs, ignore_kwargs=self.ignore_kwargs))

        wrapper.invalidate = _invalidate
        return wrapper

    async def decorator(self, func, *args, **kwargs):
        key = self.key_builder(args, kwargs, ignore_kwargs=self.ignore_kwargs)
        try:
            value = await self.cache.get(key)
        except Exception:
            value = func(*args, **kwargs)

            if inspect.isawaitable(value):
                val = await value
                await self.cache.set(key, val)
                return val

            await self.cache.set(key, value)
            return value
        else:
            return value


class CacheRegistry:
    def __init__(self, *, override=True):
        self.caches = {}
        self.override = override

    def register(self, name: str, cache) -> None:
        """Registers a cache"""
        if self.override is False and name in self.caches:
            raise CacheError(f"A cache under the name of \"{name}\" is already registered!")

        self.caches[name] = cache

    def unregister(self, name: str) -> None:
        """Removes a cache from the registry

        Parameters
        ----------
        name : str
            The name of the cache to remove from the registry.
        """
        if name not in self.caches:
            raise CacheError(f"A cache under the name of \"{name}\" is not registered!")

        del self.caches[name]

    def get(self, name: str):
        """Gets a registered cache.

        Parameters
        ----------
        name : str
            The name of the cache to get
        """
        return self.caches.get(name, None)

    def rename(self, old_name: str, new_name: str) -> None:
        """Renames a registered cache

        Parameters
        ----------
        old_name : str
            The current name of the cache.
        new_name : str
            The new name of the cache.
        """
        if self.override is False and new_name in self.caches:
            raise CacheError(f"A cache under the name of \"{new_name}\" is already registered!")

        self.caches[new_name] = self.caches.pop(old_name)


def start_redis_client() -> Union[StrictRedis, Exception]:
    loop = asyncio.get_event_loop()

    try:
        pool = StrictRedis(**CONFIG['tokens']['redis'])
        # Only way to ensure the pool is connected to redis
        loop.run_until_complete(pool.ping())
    except Exception as e:
        pool = e

    return pool


registry = CacheRegistry()
