"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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
import logging

import orjson

from lightning import LightningBot, LightningCog

log = logging.getLogger(__name__)


class Dbots(LightningCog):
    async def update_stats(self):
        headers = {"Content-Type": "application/json"}
        if self.bot.config.tokens.dbots:
            data = {"guildCount": len(self.bot.guilds), "shardCount": len(self.bot.shards)}
            headers['Authorization'] = self.bot.config.tokens.dbots
            async with self.bot.aiosession.post(f"https://discord.bots.gg/api/v1/bots/{self.bot.user.id}/stats",
                                                data=orjson.dumps(data), headers=headers) as resp:
                log.info(f"Made a request to dbots and got {resp.status}")

        if self.bot.config.tokens.topgg:
            data = {"server_count": len(self.bot.guilds), "shard_count": len(self.bot.shards)}
            headers['Authorization'] = self.bot.config.tokens.topgg
            async with self.bot.aiosession.post(f"https://top.gg/api/bots/{self.bot.user.id}/stats",
                                                data=orjson.dumps(data), headers=headers) as resp:
                log.info(f"Made a request to top.gg and got {resp.status}")

    @LightningCog.listener('on_ready')
    @LightningCog.listener('on_guild_join')
    @LightningCog.listener('on_guild_remove')
    async def on_guild_event(self):
        await self.update_stats()


async def setup(bot: LightningBot):
    if not bot.config.tokens.dbots or not bot.config.tokens.topgg:
        log.info("Not loading dbots cog because a dbots token is missing.")
        return

    await bot.add_cog(Dbots(bot))
