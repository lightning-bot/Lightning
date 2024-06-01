"""
Lightning.py - A Discord bot
Copyright (C) 2019-2024 LightSage

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
from prometheus_client import Counter, Gauge

from lightning import LightningBot, LightningCog

EVENT_LABELS = ['APPLICATION_COMMAND_CREATE',
                'APPLICATION_COMMAND_PERMISSIONS_UPDATE',
                'APPLICATION_COMMAND_UPDATE',
                'AUTO_MODERATION_ACTION_EXECUTION',
                'AUTO_MODERATION_RULE_CREATE',
                'AUTO_MODERATION_RULE_UPDATE',
                'CHANNEL_CREATE',
                'CHANNEL_DELETE',
                'CHANNEL_PINS_UPDATE',
                'CHANNEL_UPDATE',
                'GIFT_CODE_UPDATE',
                'GUILD_APPLICATION_COMMAND_COUNTS_UPDATE',
                'GUILD_APPLICATION_COMMAND_INDEX_UPDATE',
                'GUILD_AUDIT_LOG_ENTRY_CREATE',
                'GUILD_BAN_ADD',
                'GUILD_BAN_REMOVE',
                'GUILD_CREATE',
                'GUILD_DELETE',
                'GUILD_EMOJIS_UPDATE',
                'GUILD_INTEGRATIONS_UPDATE',
                'GUILD_JOIN_REQUEST_DELETE',
                'GUILD_JOIN_REQUEST_UPDATE',
                'GUILD_MEMBERS_CHUNK',
                'GUILD_MEMBER_ADD',
                'GUILD_MEMBER_REMOVE',
                'GUILD_MEMBER_UPDATE',
                'GUILD_ROLE_CREATE',
                'GUILD_ROLE_DELETE',
                'GUILD_ROLE_UPDATE',
                'GUILD_SCHEDULED_EVENT_CREATE',
                'GUILD_SCHEDULED_EVENT_DELETE',
                'GUILD_SCHEDULED_EVENT_UPDATE',
                'GUILD_SCHEDULED_EVENT_USER_ADD',
                'GUILD_SCHEDULED_EVENT_USER_REMOVE',
                'GUILD_SOUNDBOARD_SOUNDS_UPDATE',
                'GUILD_SOUNDBOARD_SOUND_CREATE',
                'GUILD_SOUNDBOARD_SOUND_DELETE',
                'GUILD_SOUNDBOARD_SOUND_UPDATE',
                'GUILD_STICKERS_UPDATE',
                'GUILD_UPDATE',
                'INTEGRATION_CREATE',
                'INTEGRATION_DELETE',
                'INTEGRATION_UPDATE',
                'INTERACTION_CREATE',
                'MESSAGE_CREATE',
                'MESSAGE_DELETE',
                'MESSAGE_DELETE_BULK',
                'MESSAGE_REACTION_ADD',
                'MESSAGE_REACTION_REMOVE',
                'MESSAGE_REACTION_REMOVE_ALL',
                'MESSAGE_REACTION_REMOVE_EMOJI',
                'MESSAGE_UPDATE',
                'PRESENCES_REPLACE',
                'PRESENCE_UPDATE',
                'READY',
                'RESUMED',
                'STAGE_INSTANCE_CREATE',
                'STAGE_INSTANCE_DELETE',
                'STAGE_INSTANCE_UPDATE',
                'THREAD_CREATE',
                'THREAD_DELETE',
                'THREAD_LIST_SYNC',
                'THREAD_MEMBERS_UPDATE',
                'THREAD_MEMBER_UPDATE',
                'THREAD_UPDATE',
                'TYPING_START',
                'USER_UPDATE',
                'WEBHOOKS_UPDATE']

GUILD_COUNT_GAUGE = Gauge("lightning_guild_count", "Bot guild growth")
LATENCY_GAUGE = Gauge("lightning_discord_shard_latency", "Latency", ['shard'])
SOCKET_EVENTS_COUNTER = Counter("lightning_socket_events", "All socket events observed", ['event'])


class Prometheus(LightningCog):
    async def cog_load(self):
        for label in EVENT_LABELS:
            SOCKET_EVENTS_COUNTER.labels(event=label)
        self.bot.loop.create_task(self.init_counters())
        self.prom_lat = self.connection_latency.start()
        self.web_counters = self.update_web_counts.start()

    def cog_unload(self):
        self.prom_lat.cancel()
        self.web_counters.cancel()

    @tasks.loop(seconds=10)
    async def connection_latency(self):
        for shard, latency in self.bot.latencies:
            LATENCY_GAUGE.labels(shard).set(latency)

    @tasks.loop(minutes=5)
    async def update_web_counts(self):
        await self.bot.redis_pool.set("lightning:stats:guild_count", len(self.bot.guilds))
        await self.bot.redis_pool.set("lightning:stats:user_count", len(self.bot.users))

    @LightningCog.listener()
    async def on_socket_event_type(self, event: str):
        SOCKET_EVENTS_COUNTER.labels(event=event).inc()

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
