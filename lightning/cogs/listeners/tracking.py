"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

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

import asyncio
from datetime import datetime
from typing import Tuple

import discord
from discord.ext import tasks

from lightning import LightningBot, LightningCog

PSQL_LIMIT = 65535


class Tracking(LightningCog):
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self._members_last_spoke: dict[Tuple[int, int], dict[str, datetime]] = {}
        self._last_spoke_lock = asyncio.Lock()
        self.do_bulk_insert_loop.start()

    async def cog_unload(self) -> None:
        self.do_bulk_insert_loop.stop()

    # Tracking User First & Last Spoke State.
    # Discord does not give me any methods to do so, so I track it myself.
    async def insert_bulk_last_spoke(self):
        async with self._last_spoke_lock:
            data = self._members_last_spoke.copy()
            self._members_last_spoke.clear()

        if not data:
            # No data to insert
            return

        query = """INSERT INTO spoke_tracking (user_id, guild_id, last_spoke_at, first_spoke_at)
                   SELECT data.user_id, data.guild_id, data.last_timestamp, data.first_timestamp
                   FROM jsonb_to_recordset($1::jsonb) AS
                    data(user_id BIGINT, guild_id BIGINT, first_timestamp TIMESTAMP, last_timestamp TIMESTAMP)
                   ON CONFLICT (user_id, guild_id) DO UPDATE
                   SET last_spoke_at = EXCLUDED.last_spoke_at,
                       first_spoke_at = LEAST(spoke_tracking.first_spoke_at, EXCLUDED.first_spoke_at);
                """
        async with self.bot.pool.acquire() as connection:
            async with connection.transaction():
                for chunk in discord.utils.as_chunks(data.items(), PSQL_LIMIT // 3):
                    records = [{"user_id": user_id, "guild_id": guild_id,
                                "first_timestamp": timestamps['first'].isoformat(),
                                "last_timestamp": timestamps['last'].isoformat()}
                               for (guild_id, user_id), timestamps in chunk]
                    await connection.execute(query, records)

    @tasks.loop(seconds=5.0)
    async def do_bulk_insert_loop(self):
        await self.insert_bulk_last_spoke()

    async def put_member_spoke(self, guild_id: int, user_id: int, timestamp: datetime):
        await self.bot.redis_pool.set(f"lightning:last_sent:{guild_id}:{user_id}",
                                      timestamp.isoformat())
        await self.bot.redis_pool.set(f"lightning:first_sent:{guild_id}:{user_id}",
                                      timestamp.isoformat(), nx=True)

        async with self._last_spoke_lock:
            dt = timestamp.replace(tzinfo=None)
            key = (guild_id, user_id)
            # If our key doesn't exist, we probably don't have a first timestamp recorded yet.
            # We'll let the db handle that complication.
            if key not in self._members_last_spoke:
                self._members_last_spoke[key] = {"first": dt, "last": dt}
            else:
                # Key exists, so first already exists.
                self._members_last_spoke[key]["last"] = dt

    @LightningCog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if not message.guild:
            return

        if message.type is discord.MessageType.new_member:
            return

        await self.put_member_spoke(message.guild.id, message.author.id, message.created_at)

    @LightningCog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot:
            return

        if not after.guild:
            return

        if before.content == after.content:
            return

        edited_at = after.edited_at or discord.utils.utcnow()

        await self.put_member_spoke(after.guild.id, after.author.id, edited_at)


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(Tracking(bot))
