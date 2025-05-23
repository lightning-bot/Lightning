"""
Lightning.py - A Discord bot
Copyright (C) 2019-2025 LightSage

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
from lightning.cogs.modlog.utils import (generate_message_embed,
                                         human_friendly_log_names)
from lightning.constants import LIGHTNING_COLOR
from lightning.events import LightningAutoModInfractionEvent
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
        await ui.Logging(channel, context=ctx, timeout=180.0).start(wait=False)

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

    # Bot events
    @LightningCog.listener()
    async def on_command_completion(self, ctx: LightningContext) -> None:
        if ctx.guild is None:
            return

        async for emitter, record in self.get_records(ctx.guild, LoggingType.COMMAND_RAN):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = False if record['format'] == "minimal without timestamp" else True
                fmt = modlogformats.MinimalisticFormat.command_ran(ctx, with_timestamp=arg)
                await emitter.send(fmt)
            elif record['format'] == "emoji":
                fmt = modlogformats.EmojiFormat.command_ran(ctx)
                await emitter.send(fmt, allowed_mentions=discord.AllowedMentions(users=[ctx.author]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.command_ran(ctx)
                await emitter.send(embed=embed)

    async def handle_automod_events(self, event_name: str, event: LightningAutoModInfractionEvent):
        msg_embed = generate_message_embed(event.message)

        async for emitter, record in self.get_records(event.guild, LoggingType(event_name)):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                fmt = modlogformats.MinimalisticFormat.from_action(event.action)
                arg = False if record['format'] == "minimal without timestamp" else True
                msg = fmt.format_message(with_timestamp=arg)
                await emitter.send(msg, embed=msg_embed)
            elif record['format'] == "emoji":
                fmt = modlogformats.EmojiFormat.from_action(event.action)
                msg = fmt.format_message()
                await emitter.send(msg, embed=msg_embed,
                                   allowed_mentions=discord.AllowedMentions(users=[event.action.target,
                                                                                   event.action.moderator]))
            elif record['format'] == "embed":
                fmt = modlogformats.EmbedFormat.from_action(event.action)
                embed = fmt.format_message()
                await emitter.send(embeds=[embed, msg_embed])

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
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                fmt = modlogformats.MinimalisticFormat.from_action(event.action)
                arg = False if record['format'] == "minimal without timestamp" else True
                msg = fmt.format_message(with_timestamp=arg)
                await emitter.send(msg)
            elif record['format'] == "emoji":
                fmt = modlogformats.EmojiFormat.from_action(event.action)
                msg = fmt.format_message()
                await emitter.send(msg,
                                   allowed_mentions=discord.AllowedMentions(users=[event.action.target,
                                                                                   event.action.moderator]))
            elif record['format'] == "embed":
                fmt = modlogformats.EmbedFormat.from_action(event.action)
                embed = fmt.format_message()
                await emitter.send(embed=embed)

    @LightningCog.listener()
    async def on_lightning_timed_moderation_action_done(self, action, guild_id, user, moderator, timer):
        async for emitter, record in self.get_records(guild_id, LoggingType(f"MEMBER_{action.upper()}")):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = False if record['format'] == "minimal without timestamp" else True
                message = modlogformats.MinimalisticFormat.timed_action_expired(action.lower(), user, moderator,
                                                                                timer.created_at, timer.expiry,
                                                                                with_timestamp=arg)
                await emitter.send(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.timed_action_expired(action.lower(), user, moderator,
                                                                         timer.created_at)
                await emitter.send(message, allowed_mentions=discord.AllowedMentions(users=[user, moderator]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.timed_action_expired(action.lower(), moderator, user,
                                                                       timer.created_at)
                await emitter.send(embed=embed)

    # Member events
    async def _log_member_join_leave(self, member, event):
        await self.bot.wait_until_ready()

        guild = member.guild
        async for emitter, record in self.get_records(guild, event):
            if record['format'] == "minimal with timestamp":
                message = modlogformats.MinimalisticFormat.join_leave(str(event), member)
                await emitter.put(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.join_leave(str(event), member)
                await emitter.put(message, allowed_mentions=discord.AllowedMentions(users=[member]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.join_leave(str(event), member)
                await emitter.put(embed=embed)

    @LightningCog.listener()
    async def on_member_join(self, member):
        await self._log_member_join_leave(member, LoggingType.MEMBER_JOIN)

    @LightningCog.listener()
    async def on_member_remove(self, member):
        await self._log_member_join_leave(member, LoggingType.MEMBER_LEAVE)

    @LightningCog.listener()
    async def on_lightning_member_passed_screening(self, member):
        async for emitter, record in self.get_records(member.guild, LoggingType.MEMBER_SCREENING_COMPLETE):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = False if record['format'] == "minimal without timestamp" else True
                message = modlogformats.MinimalisticFormat.completed_screening(member, with_timestamp=arg)
                await emitter.put(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.completed_screening(member)
                await emitter.put(message, allowed_mentions=discord.AllowedMentions(users=[member]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.completed_screening(member)
                await emitter.put(embed=embed)

    async def _log_role_changes(self, ltype: LoggingType, event: MemberRolesUpdateEvent) -> None:
        async for emitter, record in self.get_records(event.guild.id, ltype):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = False if record['format'] == "minimal without timestamp" else True
                message = modlogformats.MinimalisticFormat.role_change(event,
                                                                       with_timestamp=arg)
                await emitter.send(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.role_change(event)
                await emitter.put(message)
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.role_change(event)
                await emitter.put(embed=embed)

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
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = False if record['format'] == "minimal without timestamp" else True
                message = modlogformats.MinimalisticFormat.nick_change(event.after, event.before.nick, event.after.nick,
                                                                       event.moderator, with_timestamp=arg)
                await emitter.put(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.nick_change(event.after, event.before.nick, event.after.nick,
                                                                event.moderator)
                await emitter.put(message, allowed_mentions=discord.AllowedMentions(users=[event.after]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.nick_change(event.after, event.before.nick, event.after.nick,
                                                              event.moderator)
                await emitter.put(embed=embed)

    @LightningCog.listener()
    async def on_lightning_infraction_update(self, event: InfractionUpdateEvent):
        async for emitter, record in self.get_records(event.after.guild, LoggingType.INFRACTION_UPDATE):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = record['format'] != "minimal without timestamp"
                message = modlogformats.MinimalisticFormat.infraction_update(event, with_timestamp=arg)
                await emitter.put(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.infraction_update(event)
                await emitter.put(message)
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.infraction_update(event)
                await emitter.put(embed=embed)

    @LightningCog.listener()
    async def on_lightning_infraction_delete(self, event: InfractionDeleteEvent):
        details = event.format_infraction()
        async for emitter, record in self.get_records(event.moderator.guild, LoggingType.INFRACTION_DELETE):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = record['format'] != "minimal without timestamp"
                message = modlogformats.MinimalisticFormat.infraction_delete(event, with_timestamp=arg)
                await emitter.put(message, embed=details)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.infraction_delete(event)
                await emitter.put(message, embed=details,
                                  allowed_mentions=discord.AllowedMentions(users=[event.moderator]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.infraction_delete(event)
                await emitter.put(embeds=[embed, details])

    @LightningCog.listener()
    async def on_lightning_member_timeout_remove(self, event: AuditLogTimeoutEvent | MemberUpdateEvent):
        query = "UPDATE infractions SET active='f' WHERE action='10' AND guild_id=$1 AND user_id=$2;"
        await self.bot.pool.execute(query, event.guild.id, event.member.id)

        async for emitter, record in self.get_records(event.guild, LoggingType.MEMBER_TIMEOUT_REMOVE):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = record['format'] != "minimal without timestamp"
                message = modlogformats.MinimalisticFormat.timeout_expired(event,
                                                                           with_timestamp=arg)
                await emitter.put(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.timeout_expired(event)
                await emitter.put(message,
                                  allowed_mentions=discord.AllowedMentions(users=[event.member]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.timeout_expired(event)
                await emitter.put(embeds=[embed])

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
