"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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
from __future__ import annotations

from datetime import timedelta
from typing import Callable, Union

import aioredis
from discord import Message
from discord.ext.commands import BucketType


class RedisCooldown:
    __slots__ = ('key', 'rate', 'per', 'redis')

    def __init__(self, key: str, rate: int, per: float, redis: aioredis.Redis) -> None:
        self.key: str = key
        self.rate: int = rate
        self.per: float = per
        self.redis: aioredis.Redis = redis

    async def hit(self) -> bool:
        """
        "Hits" the key with a new increment.

        Returns
        -------
        bool
            Whether the key has hit the limit or not
        """
        current = await self.redis.get(self.key)
        if not current:
            value = await self.redis.incr(self.key)
            await self.redis.expire(self.key, self.per)
        else:
            value = await self.redis.incr(self.key)

        return value >= self.rate

    def __repr__(self) -> str:
        return f'<RedisCooldown rate: {self.rate} per: {self.per}>'


class AutoModCooldown(RedisCooldown):
    # A key should be something like "automod:guild_id:type"
    def __init__(self, key: str, rate: float, per: float, redis: aioredis.Redis,
                 bucket_type: Union[BucketType, Callable]) -> None:
        super().__init__(key, rate, per, redis)
        self.bucket_type = bucket_type
        self.per = timedelta(seconds=self.per)

    def _key_maker(self, message: Message) -> str:
        if callable(self.bucket_type):
            args = [str(arg) for arg in self.bucket_type(message)]
            return f"{self.key}:{':'.join(args)}"

        if self.bucket_type.member:
            return f"{self.key}:{message.author.id}"

    async def hit(self, message: Message):
        key = self._key_maker(message)

        current = await self.redis.get(key)
        value = await self.redis.incr(key)

        if not current:
            await self.redis.expire(key, self.per)

        return value >= self.rate