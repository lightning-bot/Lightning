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

from typing import TYPE_CHECKING, Dict, List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       LightningContext, LoggingType, hybrid_group)
from lightning.cache import Strategy, cached
from lightning.cogs.modlog import ui
from lightning.cogs.modlog.utils import human_friendly_log_names
from lightning.constants import LIGHTNING_COLOR
from lightning.events import LightningAutoModInfractionEvent
from lightning.formatters import truncate_text
from lightning.models import LoggingConfig, PartialGuild
from lightning.utils import modlogformats
from lightning.utils.checks import hybrid_guild_permissions, is_server_manager
from lightning.utils.emitters import TextChannelEmitter
from lightning.utils.time import ShortTime

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

    # TODO: Log changes to infractions
    # I suppose I could use temp ids for a cache like thing?

    def cog_unload(self):
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

    # Every event ends up here once it's formatted. Text formats get sent as a message, embeds
    # get sent as an embed, and anything extra (like the offending message) tags along as embeds.
    async def _emit(self, emitter: TextChannelEmitter, fmt_name: str, result: str | discord.Embed, *,
                    extra_embeds: Optional[List[discord.Embed]] = None, mentions: Optional[list] = None) -> None:
        extra_embeds = extra_embeds or []
        if isinstance(result, discord.Embed):
            await emitter.put(embeds=[result, *extra_embeds])
            return

        kwargs = {}
        if extra_embeds:
            kwargs['embeds'] = extra_embeds
        # Only the emoji format actually pings people, so it's the only one that needs the allowed mentions
        if fmt_name == "emoji" and mentions:
            kwargs['allowed_mentions'] = discord.AllowedMentions(users=mentions)
        await emitter.put(result, **kwargs)

    # Bot events
    @LightningCog.listener()
    async def on_command_completion(self, ctx: LightningContext) -> None:
        if ctx.guild is None:
            return

        async for emitter, record in self.get_records(ctx.guild, LoggingType.COMMAND_RAN):
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "command_ran", ctx, **kwargs)
            await self._emit(emitter, fmt_name, result, mentions=[ctx.author])

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
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "from_action", event.action, **kwargs)
            await self._emit(emitter, fmt_name, result, extra_embeds=[msg_embed] if msg_embed else [],
                             mentions=[event.action.target, event.action.moderator])

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
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "from_action", event.action, **kwargs)
            await self._emit(emitter, fmt_name, result, mentions=[event.action.target, event.action.moderator])

    @LightningCog.listener()
    async def on_lightning_timed_moderation_action_done(self, action, guild_id, user, moderator, timer):
        async for emitter, record in self.get_records(guild_id, LoggingType(f"MEMBER_{action.upper()}")):
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            # The args are a bit different for each format, so we sort that out here
            if fmt_name == "minimal":
                args = (action.lower(), user, moderator, timer.created_at, timer.expiry)
            elif fmt_name == "embed":
                args = (action.lower(), moderator, user, timer.created_at)
            else:
                args = (action.lower(), user, moderator, timer.created_at)
            result = modlogformats.format_event(fmt_name, "timed_action_expired", *args, **kwargs)
            await self._emit(emitter, fmt_name, result, mentions=[user, moderator])

    # Member events
    async def _log_member_join_leave(self, member, event):
        await self.bot.wait_until_ready()

        guild = member.guild
        async for emitter, record in self.get_records(guild, event):
            # join_leave has always skipped the timestampless minimal format, so we keep skipping it
            if record['format'] == "minimal without timestamp":
                continue
            fmt_name, _ = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "join_leave", str(event), member)
            await self._emit(emitter, fmt_name, result, mentions=[member])

    @LightningCog.listener()
    async def on_member_join(self, member):
        await self._log_member_join_leave(member, LoggingType.MEMBER_JOIN)

    @LightningCog.listener()
    async def on_member_remove(self, member):
        await self._log_member_join_leave(member, LoggingType.MEMBER_LEAVE)

    @LightningCog.listener()
    async def on_lightning_member_passed_screening(self, member):
        async for emitter, record in self.get_records(member.guild, LoggingType.MEMBER_SCREENING_COMPLETE):
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "completed_screening", member, **kwargs)
            await self._emit(emitter, fmt_name, result, mentions=[member])

    async def _log_role_changes(self, ltype: LoggingType, event: MemberRolesUpdateEvent) -> None:
        async for emitter, record in self.get_records(event.guild.id, ltype):
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "role_change", event, **kwargs)
            await self._emit(emitter, fmt_name, result)

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
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "nick_change", event.after, event.before.nick,
                                                event.after.nick, event.moderator, **kwargs)
            await self._emit(emitter, fmt_name, result, mentions=[event.after])

    @LightningCog.listener()
    async def on_lightning_infraction_update(self, event: InfractionUpdateEvent):
        async for emitter, record in self.get_records(event.after.guild, LoggingType.INFRACTION_UPDATE):
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "infraction_update", event, **kwargs)
            await self._emit(emitter, fmt_name, result)

    @LightningCog.listener()
    async def on_lightning_infraction_delete(self, event: InfractionDeleteEvent):
        details = event.format_infraction()
        async for emitter, record in self.get_records(event.moderator.guild, LoggingType.INFRACTION_DELETE):
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "infraction_delete", event, **kwargs)
            await self._emit(emitter, fmt_name, result, extra_embeds=[details], mentions=[event.moderator])

    @LightningCog.listener()
    async def on_lightning_member_timeout_remove(self, event: AuditLogTimeoutEvent | MemberUpdateEvent):
        query = "UPDATE infractions SET active='f' WHERE action='10' AND guild_id=$1 AND user_id=$2;"
        await self.bot.pool.execute(query, event.guild.id, event.member.id)

        async for emitter, record in self.get_records(event.guild, LoggingType.MEMBER_TIMEOUT_REMOVE):
            fmt_name, kwargs = modlogformats.parse_format_setting(record['format'])
            result = modlogformats.format_event(fmt_name, "timeout_expired", event, **kwargs)
            await self._emit(emitter, fmt_name, result, mentions=[event.member])

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

        for channel in guild.text_channels:
            self._close_emitter(channel.id)

        await self.get_logging_record.invalidate(guild.id)  # :meowsad:
