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

from typing import TYPE_CHECKING, Dict, Optional, Union

import discord

from lightning import LightningCog, LoggingType
from lightning.cache import Strategy, cached
from lightning.models import LoggingConfig, PartialGuild
from lightning.utils import modlogformats
from lightning.utils.emitters import TextChannelEmitter

if TYPE_CHECKING:
    from lightning import LightningBot, LightningContext
    from lightning.events import (AuditLogModAction, InfractionEvent,
                                  MemberRolesUpdateEvent, MemberUpdateEvent)


class ModLog(LightningCog):
    """Mod Logging. Like it says.

    Infractions should be inserted here as it's part of logging."""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self._emitters: Dict[int, TextChannelEmitter] = {}

    # TODO: Log changes to infractions, temporary shushing of modlog channels

    def cog_unload(self):
        for emitter in self._emitters.values():
            emitter.close()

    @cached('logging', Strategy.lru, max_size=64)
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

    async def get_records(self, guild: Union[discord.Guild, int], feature):
        """Async iterator that gets logging records for a guild

        Yields an emitter and the record"""
        if not hasattr(guild, "id"):  # This should be an int
            guild = self.bot.get_guild(guild)
            if not guild:
                return

        record = await self.get_logging_record(guild.id)
        if not record:
            return

        records = record.get_channels_with_feature(feature)
        if not records:
            return

        for channel_id, rec in records:
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

    # Moderation
    @LightningCog.listener('on_lightning_member_warn')
    @LightningCog.listener('on_lightning_member_kick')
    @LightningCog.listener('on_lightning_member_ban')
    @LightningCog.listener('on_lightning_member_unban')
    @LightningCog.listener('on_lightning_member_mute')
    @LightningCog.listener('on_lightning_member_unmute')
    async def on_lightning_member_action(self, event: Union[AuditLogModAction, InfractionEvent]):
        if not event.action.is_logged():
            await event.action.add_infraction(self.bot.pool)

        event_name = f"MEMBER_{event.action.event}" if not hasattr(event, "event_name") else f"MEMBER_{str(event)}"

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
        async for emitter, record in self.get_records(guild_id, action):
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

    async def _log_role_changes(self, ltype: LoggingType, guild, member, *, added=None, removed=None,
                                entry=None) -> None:
        async for emitter, record in self.get_records(guild, ltype):
            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = False if record['format'] == "minimal without timestamp" else True
                message = modlogformats.MinimalisticFormat.role_change(member, added, removed, entry=entry,
                                                                       with_timestamp=arg)
                await emitter.send(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.role_change(added, removed, member, entry=entry)
                await emitter.put(message)
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.role_change(member, added, removed, entry=entry)
                await emitter.put(embed=embed)

    @LightningCog.listener()
    async def on_lightning_member_role_change(self, event: MemberRolesUpdateEvent):
        if event.added_roles:
            await self._log_role_changes(LoggingType.MEMBER_ROLE_ADD, event.guild, event.after, added=event.added_roles,
                                         entry=event.entry)

        if event.removed_roles:
            await self._log_role_changes(LoggingType.MEMBER_ROLE_REMOVE, event.guild, event.after,
                                         removed=event.removed_roles, entry=event.entry)

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


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(ModLog(bot))
