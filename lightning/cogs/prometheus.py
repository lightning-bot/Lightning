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
from __future__ import annotations

from discord.ext import tasks
from prometheus_async import aio
from prometheus_client import Gauge

from lightning import LightningBot, LightningCog

GUILD_COUNT_GAUGE = Gauge("lightning_guild_count", "Bot guild growth")
LATENCY_GAUGE = Gauge("lightning_discord_shard_latency", "Latency", ['shard'])


class Prometheus(LightningCog):
    async def cog_load(self):
        self.bot.loop.create_task(self.init_counters())
        self.prom_lat = self.connection_latency.start()

    def cog_unload(self):
        self.prom_lat.cancel()

    @tasks.loop(seconds=10)
    async def connection_latency(self):
        for shard, latency in self.bot.latencies:
            LATENCY_GAUGE.labels(shard).set(latency)

    async def init_counters(self):
        await self.bot.wait_until_ready()
        GUILD_COUNT_GAUGE.set(len(self.bot.guilds))

        await aio.web.start_http_server(port=self.bot.config.tokens.prometheus.port)

    @LightningCog.listener()
    async def on_lightning_guild_join(self, guild):
        GUILD_COUNT_GAUGE.inc()

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild):
        GUILD_COUNT_GAUGE.dec()


async def setup(bot: LightningBot):
    await bot.add_cog(Prometheus(bot))
