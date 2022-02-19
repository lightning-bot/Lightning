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

from typing import TYPE_CHECKING

import discord

from lightning import LightningCog
from lightning.models import PartialGuild

if TYPE_CHECKING:
    from typing import Union

    from lightning import LightningBot


class State(LightningCog):
    # There is no way to know when the bot has left or joined servers while being offline.
    # This aims to solve those issues by replacing the on_guild_join and on_guild_remove with
    # our own listeners.

    @LightningCog.listener()
    async def on_ready(self) -> None:
        records = await self.bot.pool.fetch("SELECT id, whitelisted FROM guilds WHERE left_at IS NULL;")

        for record in records:
            guild = self.bot.get_guild(record['id'])
            if guild is not None:
                if record['whitelisted'] is False:
                    await guild.leave()
                continue
            await self.remove_guild(record['id'])

    async def get_guild_record(self, guild_id: int) -> PartialGuild:
        record = await self.bot.pool.fetchrow("SELECT * FROM guilds WHERE id=$1", guild_id)
        return PartialGuild(record)

    async def remove_guild(self, guild: Union[int, discord.Guild, PartialGuild]) -> None:
        guild_id = getattr(guild, 'id', guild)
        await self.bot.pool.execute("UPDATE guilds SET left_at=(NOW() AT TIME ZONE 'utc') WHERE id=$1", guild_id)

        if not isinstance(guild, discord.Guild):
            guild = await self.get_guild_record(guild_id)

        self.bot.dispatch("lightning_guild_remove", guild)

    async def add_guild(self, guild: discord.Guild) -> None:
        async with self.bot.pool.acquire() as con:
            query = """SELECT true FROM guilds WHERE id=$1 AND left_at IS NULL;"""
            registered = await con.fetchval(query, guild.id)
            query = """SELECT whitelisted FROM guilds WHERE id=$1;"""  # should probably do this in a subquery
            whitelisted = await con.fetchval(query, guild.id)
            query = """INSERT INTO guilds (id, name, owner_id)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (id) DO UPDATE
                       SET name = EXCLUDED.name, owner_id = EXCLUDED.owner_id, left_at = NULL;
                    """
            await con.execute(query, guild.id, guild.name, guild.owner_id)

        if whitelisted is False:
            await guild.leave()
            # will dispatch guild_remove
            return

        if not registered:
            self.bot.dispatch("lightning_guild_add", guild)

    @LightningCog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.remove_guild(guild)

    @LightningCog.listener('on_guild_join')
    @LightningCog.listener('on_guild_available')
    async def on_guild_add(self, guild: discord.Guild) -> None:
        await self.add_guild(guild)

    @LightningCog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if before.name != after.name:
            await self.add_guild(after)

        if before.owner_id != after.owner_id:
            await self.add_guild(after)


def setup(bot: LightningBot) -> None:
    bot.add_cog(State(bot))
