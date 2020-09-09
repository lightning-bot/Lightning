"""
Lightning.py - A multi-purpose Discord bot
Copyright (C) 2020 - LightSage

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
import logging
import time
from functools import wraps
from typing import Optional

import toml
from aredis import StrictRedis
from lru import LRU


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
    """Base cache class"""

    def __init__(self, name: str, *, key_builder=None, should_build_key=True):
        self.name = name
        self.key_builder = key_builder or self._make_key
        self.should_build_key = should_build_key
        # I kinda don't like this but whatever.
        registry.register(name, self)

    def _make_key(self, key, *args, **kwargs) -> str:
        return str(key)

    async def _get(self, key):
        raise NotImplementedError

    async def get(self, key):
        """Gets a key from cache"""
        if self.should_build_key:
            key = self.key_builder(key)
        return await self._get(key)

    async def get_or_default(self, key, *, default=None):
        """Gets a key from cache.

        If the key is not cached, returns the default.
        """
        if self.should_build_key:
            key = self.key_builder(key)
        value = await self._get(key)
        return value if value is not None else default

    async def _set(self, key, value):
        raise NotImplementedError

    async def set(self, key, value):
        """Sets a key into cache"""
        if self.should_build_key:
            key = self.key_builder(key)
        await self._set(key, value)

    async def _invalidate(self, key):
        raise NotImplementedError

    async def invalidate(self, key):
        """Invalidates a key from cache"""
        if self.should_build_key:
            key = self.key_builder(key)
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

    async def _invalidate(self, key) -> None:
        del self._cache[key]

    async def _clear(self) -> None:
        self._cache.clear()


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
        if redis_pool is None:
            raise Exception("Redis is not initialized")
        self.pool = redis_pool
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


class cached:
    def __init__(self, name, strategy=Strategy.raw, *, rename_to_func=False, **kwargs):
        key_builder = self.deco_key_builder
        self.rename_to_func = rename_to_func

        kwargs.update({"key_builder": key_builder, "should_build_key": False})

        self.cache = strategy.value[1](name, **kwargs)

    # deco_key_builder is provided by Rapptz under the function name of _make_key
    # Copyright ©︎ 2015 Rapptz - MIT License
    # https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/cache.py#L62
    @staticmethod
    def deco_key_builder(func, args, kwargs):
        # this is a bit of a cluster fuck
        # we do care what 'self' parameter is when we __repr__ it
        def _true_repr(o):
            if o.__class__.__repr__ is object.__repr__:
                return f'<{o.__class__.__module__}.{o.__class__.__name__}>'
            return repr(o)

        key = [f'{func.__module__}.{func.__name__}']
        key.extend(_true_repr(o) for o in args)

        return ':'.join(key)

    def __call__(self, func):
        if self.rename_to_func is True:
            registry.rename(self.cache.name, f'{func.__module__}.{func.__name__}')

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.decorator(func, *args, **kwargs)
        wrapper._cache = self
        return wrapper

    async def decorator(self, func, *args, **kwargs):
        key = self.cache.key_builder(func, args, kwargs)
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

    def register(self, name, cache):
        """Registers a cache"""
        if self.override is False and name in self.caches:
            raise CacheError(f"A cache under the name of \"{name}\" is already registered!")

        self.caches[name] = cache

    def unregister(self, name):
        """Removes a cache from the registry"""
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

    def rename(self, old_name, new_name):
        """Renames a registered cache"""
        if self.override is False and new_name in self.caches:
            raise CacheError(f"A cache under the name of \"{new_name}\" is already registered!")

        self.caches[new_name] = self.caches.pop(old_name)


def start_redis_client() -> Optional[StrictRedis]:
    log = logging.getLogger("lightning.cache.start_redis_client")

    loop = asyncio.get_event_loop()
    config = toml.load(open('config.toml', 'r'))

    try:
        pool = StrictRedis(**config['tokens']['redis'])
        # Only way to ensure the pool is connected to redis
        loop.run_until_complete(pool.ping())
    except Exception as e:
        log.warning(f"Unable to connect to redis {e}")
        pool = None

    return pool


redis_pool = start_redis_client()
registry = CacheRegistry()
