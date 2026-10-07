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

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       LightningContext, LoggingType, hybrid_group,
                       modlogformats)
from lightning.cache import Strategy, cached
from lightning.cogs.modlog import ui
from lightning.cogs.modlog.timeouts import TimeoutState, TimeoutStateCache
from lightning.cogs.modlog.utils import human_friendly_log_names
from lightning.constants import LIGHTNING_COLOR
from lightning.events import (CommandEvent, LightningAutoModInfractionEvent,
                              MemberJoinEvent, MemberLeaveEvent,
                              MemberScreeningEvent, TimedActionExpiredEvent,
                              TimeoutExpiredEvent)
from lightning.formatters import truncate_text
from lightning.models import LoggingConfig, PartialGuild
from lightning.utils.checks import hybrid_guild_permissions, is_server_manager
from lightning.utils.emitters import TextChannelEmitter
from lightning.utils.time import ShortTime, strip_tzinfo

if TYPE_CHECKING:
    from lightning.events import (AuditLogModAction, AuditLogTimeoutEvent,
                                  InfractionDeleteEvent, InfractionEvent,
                                  InfractionUpdateEvent,
                                  MemberRolesUpdateEvent, MemberUpdateEvent)


class ModLog(LightningCog):
    """Commands to manage the server's modlog(s)"""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self._emitters: Dict[int, TextChannelEmitter] = {}
        self.shushed: List[int] = []  # shushed channels
        self.timeouts = TimeoutStateCache()
        self.purge_timeouts.start()

    def get_timeout_state(self, guild_id: int, user_id: int) -> Optional[TimeoutState]:
        """Returns the cached state of an active timeout, if any"""
        return self.timeouts.get(guild_id, user_id)

    async def _deactivate_stale_timeouts(self, guild_ids: List[int]) -> None:
        """Deactivates timeout infractions that ran out while the bot wasn't watching"""
        query = """UPDATE infractions SET active='f'
                   WHERE action='10' AND active='t' AND guild_id=ANY($1) AND expiry < $2;"""
        await self.bot.pool.execute(query, guild_ids, strip_tzinfo(datetime.now(timezone.utc)))

    def _backfill_timeouts(self, guild: discord.Guild) -> None:
        for member in guild.members:
            self._backfill_member_timeout(member)

    def _backfill_member_timeout(self, member: discord.Member) -> None:
        until = member.timed_out_until
        if until is not None and until > datetime.now(timezone.utc) \
                and not self.timeouts.is_active(member.guild.id, member.id):
            self.timeouts.set(member.guild.id, member.id, until)

    @tasks.loop(minutes=1.0)
    async def purge_timeouts(self):
        for guild_id, user_id, state in self.timeouts.purge_expired():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            self.bot.dispatch("lightning_member_timeout_expired", TimeoutExpiredEvent(
                guild, guild.get_member(user_id) or discord.Object(user_id),
                discord.Object(state.moderator_id) if state.moderator_id else None,
                state.reason, state.timed_out_until))

    @purge_timeouts.before_loop
    async def before_purge_timeouts(self):
        await self.bot.wait_until_ready()

    @LightningCog.listener()
    async def on_lightning_member_timeout_expired(self, event: TimeoutExpiredEvent):
        query = "UPDATE infractions SET active='f' WHERE action='10' AND guild_id=$1 AND user_id=$2;"
        await self.bot.pool.execute(query, event.guild.id, event.user.id)

        async for emitter, record in self.get_records(event.guild, LoggingType.MEMBER_TIMEOUT_REMOVE):
            await self._emit(emitter, record, event)

    @LightningCog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            self._backfill_timeouts(guild)
        await self._deactivate_stale_timeouts([g.id for g in self.bot.guilds])

    @LightningCog.listener()
    async def on_guild_available(self, guild: discord.Guild):
        self._backfill_timeouts(guild)
        await self._deactivate_stale_timeouts([guild.id])

    @LightningCog.listener()
    async def on_lightning_member_timeout_change(self, event: MemberUpdateEvent):
        guild_id, user_id = event.after.guild.id, event.after.id
        until = event.after.timed_out_until
        if until is None or until <= datetime.now(timezone.utc):
            self.timeouts.clear(guild_id, user_id)
            return

        if event.before.timed_out_until is not None and event.before.timed_out_until != until:
            # The timeout was extended or shortened, so keep the infraction's expiry in line with Discord
            query = """UPDATE infractions SET expiry=$3
                       WHERE id = (SELECT id FROM infractions
                                   WHERE action='10' AND active='t' AND guild_id=$1 AND user_id=$2
                                   ORDER BY id DESC LIMIT 1);"""
            await self.bot.pool.execute(query, guild_id, user_id, strip_tzinfo(until))

        previous = self.timeouts.get(guild_id, user_id)
        entry = event.entry
        moderator_id = entry.user_id if entry is not None else (previous.moderator_id if previous else None)
        reason = entry.reason if entry is not None else (previous.reason if previous else None)
        self.timeouts.set(guild_id, user_id, until, moderator_id=moderator_id, reason=reason,
                          infraction_id=previous.infraction_id if previous else None)

    # TODO: Log changes to infractions
    # I suppose I could use temp ids for a cache like thing?

    def cog_unload(self):
        self.purge_timeouts.cancel()
        for emitter in self._emitters.values():
            emitter.close()

    @hybrid_group(level=CommandLevel.Admin, fallback="setup")
    @app_commands.guild_only()
    @app_commands.describe(channel="The channel to configure, defaults to the current one")
    @commands.bot_has_permissions(manage_messages=True, view_audit_log=True, send_messages=True)
    @is_server_manager()
    async def modlog(self, ctx: GuildContext, *, channel: discord.TextChannel = commands.CurrentChannel):
        """Sets up mod logging for a channel"""
        await ui.LoggingCV2(channel, context=ctx, timeout=60.0).start(wait=False)

    @modlog.command(level=CommandLevel.Admin, name='showall')
    @commands.guild_only()
    @is_server_manager()
    async def modlog_show(self, ctx: GuildContext):
        """Shows all configured mod log channels"""
        config = await self.get_logging_record(ctx.guild.id)
        if not config:
            await ctx.send("You haven't set up any channels to be mod logs!", ephemeral=True)
            return

        embed = discord.Embed(color=LIGHTNING_COLOR, title="ModLog Channels")
        for channel_id, values in config.logging.items():
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                continue

            embed.add_field(name=f"#{channel.name}",
                            value=f"**Format**: {values['format'].title()}\n"
                                  f"**Types**: {human_friendly_log_names(LoggingType(values['types']))}")

        await ctx.send(embed=embed)

    # @modlog.command(name='shush', level=CommandLevel.Admin)
    @app_commands.describe(channel="The channel to shush")
    @hybrid_guild_permissions(manage_channels=True)
    async def modlog_shush(self, ctx: GuildContext, channel: discord.TextChannel, duration: ShortTime):
        """Shushes the mod log temporarily"""
        ...

    @cached('logging', Strategy.lru, max_size=256)
    async def get_logging_record(self, guild_id: int) -> Optional[LoggingConfig]:
        """Gets a logging record.

        Parameters
        ----------
        guild_id : int
            The ID of the server

        Returns
        -------
        Optional[LoggingConfig]
            Returns the record if it exists."""
        records = await self.bot.pool.fetch("SELECT * FROM logging WHERE guild_id=$1;", guild_id)
        return LoggingConfig(records) if records else None

    async def get_records(self, guild: Union[discord.Guild, int], feature: int):
        """Async iterator that gets logging records for a guild

        Yields an emitter and the record"""
        if not hasattr(guild, "id"):  # This should be an int
            guild = self.bot.get_guild(guild)  # type: ignore
            if not guild:
                return

        record = await self.get_logging_record(guild.id)
        if not record:
            return

        records = record.get_channels_with_feature(feature)
        if not records:
            return

        for channel_id, rec in records:

            if channel_id in self.shushed:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            emitter = self._emitters.get(channel_id, None)
            if emitter is None:
                emitter = TextChannelEmitter(channel)  # At some point, we'll also do EmbedsEmitter
                self._emitters[channel_id] = emitter

            if not emitter.running():
                emitter.start()

            yield emitter, rec

    # Every event ends up here. We find the renderer for the event, then send what it gives us as a
    # message or an embed. Anything extra (like the offending message) tags along as embeds.
    async def _emit(self, emitter: TextChannelEmitter, record, event, *,
                    extra_embeds: Optional[List[discord.Embed]] = None) -> None:
        ctx = modlogformats.FormatContext.from_setting(record['format'])
        renderer = modlogformats.get_renderer(event)
        result = renderer.render(ctx)
        extra_embeds = extra_embeds or []

        if isinstance(result, discord.Embed):
            await emitter.put(embeds=[result, *extra_embeds])
            return

        kwargs = {}
        if extra_embeds:
            kwargs['embeds'] = extra_embeds
        # Only the emoji format actually pings people, so it's the only one that needs the allowed mentions
        mentions = renderer.mentions()
        if ctx.fmt == "emoji" and mentions:
            kwargs['allowed_mentions'] = discord.AllowedMentions(users=mentions)
        await emitter.put(result, **kwargs)

    # Bot events
    @LightningCog.listener()
    async def on_command_completion(self, ctx: LightningContext) -> None:
        if ctx.guild is None:
            return

        async for emitter, record in self.get_records(ctx.guild, LoggingType.COMMAND_RAN):
            await self._emit(emitter, record, CommandEvent(ctx))

    async def handle_automod_events(self, event_name: str, event: LightningAutoModInfractionEvent):
        parts = []
        if event.message:
            parts.append(event.message.content)
            parts.extend(f"\N{PAPERCLIP} {attachment.url}" for attachment in event.message.attachments)
            if event.message.embeds:
                parts.append("Message contained embeds")

        content = event.tracked_content or "\n".join(part for part in parts if part)
        msg_embed = None
        if content:
            msg_embed = discord.Embed()
            msg_embed.add_field(name="Offending message content",
                                value=truncate_text(content, 1024))

        async for emitter, record in self.get_records(event.guild, LoggingType(event_name)):
            await self._emit(emitter, record, event.action, extra_embeds=[msg_embed] if msg_embed else None)

    # Moderation
    @LightningCog.listener('on_lightning_member_warn')
    @LightningCog.listener('on_lightning_member_kick')
    @LightningCog.listener('on_lightning_member_ban')
    @LightningCog.listener('on_lightning_member_unban')
    @LightningCog.listener('on_lightning_member_mute')
    @LightningCog.listener('on_lightning_member_unmute')
    @LightningCog.listener('on_lightning_member_timeout')
    async def on_lightning_member_action(self, event: Union[AuditLogModAction, InfractionEvent]):
        if not event.action.is_logged():
            await event.action.add_infraction(self.bot.pool)

        event_name = f"MEMBER_{event.action.event}" if not hasattr(event, "event_name") else f"MEMBER_{str(event)}"

        if isinstance(event, LightningAutoModInfractionEvent):
            await self.handle_automod_events(event_name, event)
            return

        async for emitter, record in self.get_records(event.guild, LoggingType(event_name)):
            await self._emit(emitter, record, event.action)

    @LightningCog.listener()
    async def on_lightning_timed_moderation_action_done(self, action, guild_id, user, moderator, timer):
        async for emitter, record in self.get_records(guild_id, LoggingType(f"MEMBER_{action.upper()}")):
            event = TimedActionExpiredEvent(action.lower(), user, moderator, timer.created_at, timer.expiry)
            await self._emit(emitter, record, event)

    # Member events
    async def _log_member_join_leave(self, member, event, event_cls):
        await self.bot.wait_until_ready()

        guild = member.guild
        async for emitter, record in self.get_records(guild, event):
            # Join/leave has always skipped the timestampless minimal format, so we keep skipping it
            if record['format'] == "minimal without timestamp":
                continue
            await self._emit(emitter, record, event_cls(member))

    @LightningCog.listener()
    async def on_member_join(self, member):
        self._backfill_member_timeout(member)
        await self._log_member_join_leave(member, LoggingType.MEMBER_JOIN, MemberJoinEvent)

    @LightningCog.listener()
    async def on_member_remove(self, member):
        self.timeouts.clear(member.guild.id, member.id)
        await self._log_member_join_leave(member, LoggingType.MEMBER_LEAVE, MemberLeaveEvent)

    @LightningCog.listener()
    async def on_lightning_member_passed_screening(self, member):
        async for emitter, record in self.get_records(member.guild, LoggingType.MEMBER_SCREENING_COMPLETE):
            await self._emit(emitter, record, MemberScreeningEvent(member))

    async def _log_role_changes(self, ltype: LoggingType, event: MemberRolesUpdateEvent) -> None:
        async for emitter, record in self.get_records(event.guild.id, ltype):
            await self._emit(emitter, record, event)

    @LightningCog.listener()
    async def on_lightning_member_role_change(self, event: MemberRolesUpdateEvent):
        if event.added_roles:
            await self._log_role_changes(LoggingType.MEMBER_ROLE_ADD, event)

        if event.removed_roles:
            await self._log_role_changes(LoggingType.MEMBER_ROLE_REMOVE, event)

    @LightningCog.listener()
    async def on_lightning_member_nick_change(self, event: MemberUpdateEvent):
        guild = event.guild
        async for emitter, record in self.get_records(guild, LoggingType.MEMBER_NICK_CHANGE):
            await self._emit(emitter, record, event)

    @LightningCog.listener()
    async def on_lightning_infraction_update(self, event: InfractionUpdateEvent):
        async for emitter, record in self.get_records(event.after.guild, LoggingType.INFRACTION_UPDATE):
            await self._emit(emitter, record, event)

    @LightningCog.listener()
    async def on_lightning_infraction_delete(self, event: InfractionDeleteEvent):
        details = event.format_infraction()
        async for emitter, record in self.get_records(event.moderator.guild, LoggingType.INFRACTION_DELETE):
            await self._emit(emitter, record, event, extra_embeds=[details])

    @LightningCog.listener()
    async def on_lightning_member_timeout_remove(self, event: AuditLogTimeoutEvent):
        query = "UPDATE infractions SET active='f' WHERE action='10' AND guild_id=$1 AND user_id=$2;"
        await self.bot.pool.execute(query, event.guild.id, event.member.id)

        async for emitter, record in self.get_records(event.guild, LoggingType.MEMBER_TIMEOUT_REMOVE):
            await self._emit(emitter, record, event)

    @LightningCog.listener()
    async def on_lightning_guild_alert(self, guild_id: int, message: str):
        async for emitter, record in self.get_records(guild_id, LoggingType.BOT_INFO):
            if record['format'] == "embed":
                embed = discord.Embed(color=discord.Color.yellow(), description=message)
                await emitter.put(embeds=[embed])
            else:
                await emitter.put(message)

    def _close_emitter(self, channel_id: int) -> None:
        emitter = self._emitters.pop(channel_id, None)
        if emitter:
            emitter.close()

    @LightningCog.listener()
    async def on_lightning_channel_config_remove(self, event):
        if not isinstance(event.channel, discord.TextChannel):
            return

        self._close_emitter(event.channel.id)
        await self.get_logging_record.invalidate(event.guild.id)

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild):
        if isinstance(guild, PartialGuild):  # Guild was removed when the bot was down
            return

        self.timeouts.clear_guild(guild.id)

        for channel in guild.text_channels:
            self._close_emitter(channel.id)

        await self.get_logging_record.invalidate(guild.id)  # :meowsad:
