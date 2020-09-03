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

# _wrap_new_coroutine, _wrap_and_store_coroutine, ExpiringCache, cache code is provided by Rapptz under the MIT License
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


class Strategy(enum.Enum):
    lru = 1
    raw = 2
    timed = 3


def cache(maxsize=128, strategy=Strategy.lru, ignore_kwargs=False):
    def decorator(func):
        if strategy is Strategy.lru:
            _internal_cache = LRU(maxsize)
            _stats = _internal_cache.get_stats
        elif strategy is Strategy.raw:
            _internal_cache = {}
            _stats = lambda: (0, 0)  # noqa
        elif strategy is Strategy.timed:
            _internal_cache = ExpiringCache(maxsize)
            _stats = lambda: (0, 0)  # noqa

        def _make_key(args, kwargs):
            # this is a bit of a cluster fuck
            # we do care what 'self' parameter is when we __repr__ it
            def _true_repr(o):
                if o.__class__.__repr__ is object.__repr__:
                    return f'<{o.__class__.__module__}.{o.__class__.__name__}>'
                return repr(o)

            key = [f'{func.__module__}.{func.__name__}']
            key.extend(_true_repr(o) for o in args)
            if not ignore_kwargs:
                for k, v in kwargs.items():
                    # note: this only really works for this use case in particular
                    # I want to pass asyncpg.Connection objects to the parameters
                    # however, they use default __repr__ and I do not care what
                    # connection is passed in, so I needed a bypass.
                    if k == 'connection':
                        continue

                    key.append(_true_repr(k))
                    key.append(_true_repr(v))

            return ':'.join(key)

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            try:
                value = _internal_cache[key]
            except KeyError:
                value = func(*args, **kwargs)

                if inspect.isawaitable(value):
                    return _wrap_and_store_coroutine(_internal_cache, key, value)

                _internal_cache[key] = value
                return value
            else:
                if asyncio.iscoroutinefunction(func):
                    return _wrap_new_coroutine(value)
                return value

        def _invalidate(*args, **kwargs):
            try:
                del _internal_cache[_make_key(args, kwargs)]
            except KeyError:
                return False
            else:
                return True

        def _invalidate_containing(key):
            to_remove = []
            for k in _internal_cache.keys():
                if key in k:
                    to_remove.append(k)
            for k in to_remove:
                try:
                    del _internal_cache[k]
                except KeyError:
                    continue

        wrapper.cache = _internal_cache
        wrapper.get_key = lambda *args, **kwargs: _make_key(args, kwargs)
        wrapper.invalidate = _invalidate
        wrapper.get_stats = _stats
        wrapper.invalidate_containing = _invalidate_containing
        return wrapper
    return decorator


class BaseCache:
    """Base cache class"""

    def __init__(self, name: str, *, key_builder=None):
        self.name = name
        self.key_builder = key_builder or self._make_key

    def _make_key(self, key, *args, **kwargs) -> str:
        return str(key)

    async def _get(self, key):
        raise NotImplementedError

    async def get(self, key):
        """Gets a key from cache"""
        key = self.key_builder(key)
        return await self._get(key)

    async def get_or_default(self, key, *, default=None):
        """Gets a key from cache.

        If the key is not cached, returns the default.
        """
        key = self.key_builder(key)
        value = await self._get(key)
        return value if value is not None else default

    async def _set(self, key, value):
        raise NotImplementedError

    async def set(self, key, value):
        """Sets a key into cache"""
        key = self.key_builder(key)
        await self._set(key, value)

    async def _invalidate(self, key):
        raise NotImplementedError

    async def invalidate(self, key):
        """Invalidates a key from cache"""
        key = self.key_builder(key)
        await self._invalidate(key)

    async def _clear(self):
        raise NotImplementedError

    async def clear(self):
        """Clears the cache"""
        await self._clear()


class RawCache(BaseCache):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}

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


class LRUCache(RawCache):
    def __init__(self, *args, max_size=128, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = LRU(max_size)

    @property
    def stats(self):
        return self._cache.get_stats()


class TimedCache(RawCache):
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
