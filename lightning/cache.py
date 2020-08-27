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
import time
from functools import wraps
from typing import Optional

import aredis.cache
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
    redis = 4


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


class KeyGen(aredis.cache.IdentityGenerator):
    def generate(self, key, args):
        key = [f"{self.app}:{key}"]
        if args:
            key.extend(repr(o) for o in args)
        return ':'.join(key)


class Cache:
    """A cache

    Parameters
    ----------
    strategy : Strategy
        The cache strategy
    max_size : int, Optional
        Max size of the LRU cache (If the strategy is LRU).
        Defaults to 120
    **kwargs
        Kwargs

    Raises
    ------
    NotImplementedError
        Raised when some kwarg is missing for redis caching
    """
    __slots__ = ('redis', 'strategy', '_cache')

    def __init__(self, strategy=Strategy.lru, *, max_size=120, **kwargs):
        if strategy is Strategy.lru:
            _cache = LRU(max_size)
            self.redis = False
        elif strategy is Strategy.raw:
            _cache = {}
            self.redis = False
        elif strategy is Strategy.redis:
            name = kwargs.get("name", None)
            client = kwargs.get("client", None)

            if not client or not name:
                raise NotImplementedError("Missing client and/or name kwarg")

            key_generator = kwargs.pop("key_generator", KeyGen)
            compressor = kwargs.pop("compressor", None)
            serializer = kwargs.pop("serializer", None)
            _cache = RedisCache(client, name, key_generator, compressor, serializer)
            self.redis = True

        self.strategy = strategy
        self._cache = _cache

    def __call__(self, func):
        @wraps(func)
        async def _inner(*args, **kwargs):
            key = func.__name__
            res = await self.get(key, param=(args, kwargs))
            if res is None:
                res = func(*args, **kwargs)
                await self.set(key, res, param=(args, kwargs))
            return res
        _inner.cache = self
        return _inner

    async def set(self, key, value, *, expire_time: Optional[float] = None, param=None):
        """Sets a key in the cache

        Parameters
        ----------
        key :
            a key
        value :
            The value for the key
        expire_time : Optional[float]
            The optional expiry time for the key (Redis only)
        """
        if self.redis:
            await self._cache.set(key, value, param, expire_time=expire_time)
        else:
            self._cache[key] = value

    async def get(self, key, *, param=None):
        """Gets a key from cache

        Parameters
        ----------
        key
            The key to get
        param : None, Optional
            Optional parameter passed to the key builder(Redis only)

        Raises
        ------
        KeyError
            Raised when the key is not cached
        """
        if self.redis:
            value = await self._cache.get(key, param)
            # dumb hack
            if value == b'None' or value == b'null':
                return None

            if value is None:
                raise KeyError

            return value
        else:
            return self._cache[key]

    async def get_or_default(self, key, *, param=None, default=None):
        """Gets a key from cache. If the key is not cached, returns the default.

        Parameters
        ----------
        key :
            The key to get from the cache
        param : None, Optional
            Description
        default : None, Optional
            A default argument to return if the key is not in cache

        Returns
        -------
        The value of the key or default.
        """
        if self.redis:
            value = await self._cache.get(key, param)
            if value is None:
                return default
        else:
            return self._cache.get(key, default)

    async def invalidate(self, key, *, param=None) -> bool:
        """Removes a key from cache

        Parameters
        ----------
        key :
            The key to delete
        param : None, Optional
            Optional parameter passed to the key builder (Redis only)

        Returns
        -------
        bool
            A boolean indicator of whether the removal was successful or not
        """
        if not self.redis:
            try:
                del self._cache[key]
            except KeyError:
                return False
            else:
                return True

        resp = await self._cache.delete(key, param)
        if resp == 0:
            # No key
            return False
        else:
            return True

    def __repr__(self):
        return f"<Cache strategy={self.strategy.name}>"


class RedisCache(aredis.cache.Cache):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _gen_identity(self, key, kwargs=None):
        """generate identity according to key and param given"""
        if self.identity_generator:
            identity = self.identity_generator.generate(key, kwargs)
        else:
            identity = key
        return identity


class Compressor(aredis.cache.Compressor):
    def __init__(self, encoding='utf-8', min_length=25):
        self.encoding = encoding
        self.min_length = min_length
