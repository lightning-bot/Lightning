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

from typing import List, Optional, Union

import discord

from lightning.enums import ActionType
from lightning.models import Action, InfractionRecord
from lightning.utils.helpers import ticker
from lightning.utils.modlogformats import base_user_format
from lightning.utils.time import add_tzinfo

# These are event models that'll be passed for listeners cog


class BaseAuditLogEvent:
    __slots__ = ("moderator", "reason")

    def __init__(self, entry: Optional[discord.AuditLogEntry] = None):
        # We can probably get the guild.id from the entry itself...
        if entry is not None:
            self.moderator = entry.user
            self.reason = entry.reason
        else:
            self.moderator = None
            self.reason = None


# lightning_member_nick_change
class MemberUpdateEvent(BaseAuditLogEvent):
    """Represents a member update with optional audit log information"""
    __slots__ = ("before", "after", "entry")

    def __init__(self, before: discord.Member, after: discord.Member, entry: Optional[discord.AuditLogEntry]):
        super().__init__(entry)
        self.before = before
        self.after = after
        self.entry = entry

    @property
    def guild(self) -> discord.Guild:
        """A shortcut for MemberUpdateEvent.after.guild"""
        return self.after.guild

    @property
    def member(self) -> discord.Member:
        """A shortcut for MemberUpdateEvent.after"""
        return self.after


# lightning_member_role_change
class MemberRolesUpdateEvent(MemberUpdateEvent):
    @property
    def added_roles(self) -> List[discord.Role]:
        return [role for role in self.after.roles if role not in self.before.roles]

    @property
    def removed_roles(self) -> List[discord.Role]:
        return [role for role in self.before.roles if role not in self.after.roles]


# lightning_member_role_add
# lightning_member_role_remove
class MemberRoleUpdateEvent(BaseAuditLogEvent):
    __slots__ = ("role")

    def __init__(self, role: discord.Role, entry: Optional[discord.AuditLogEntry]):
        super().__init__(entry)
        self.role = role


# lightning_member_kick
# lightning_member_ban
# lightning_member_unban
class AuditLogModAction(BaseAuditLogEvent):
    """Represents a moderation event that was taken from Audit Logs

    This will also build the Action class from the parameters given."""
    __slots__ = ("member", "guild", "action")

    def __init__(self, event: Union[ActionType, str], member: Union[discord.User, discord.Member],
                 entry: discord.AuditLogEntry, *, guild: Optional[discord.Guild] = None):
        super().__init__(entry)
        self.member = member

        self.guild = guild or member.guild
        self.action = Action(self.guild.id, event, member, self.moderator, self.reason)


# lightning_member_timeout_remove
class AuditLogTimeoutEvent(AuditLogModAction):
    def __init__(self, event: Union[ActionType, str],
                 entry: discord.AuditLogEntry, *, guild: Optional[discord.Guild] = None):
        super().__init__(event, entry.target, entry, guild=guild)
        self.before = entry.before
        self.after = entry.after
        self.entry = entry


# lightning_member_mute
# lightning_member_unmute
# lightning_member_kick
# lightning_member_ban
# lightning_member_unban
class InfractionEvent:  # ModerationEvent sounded nice too...
    __slots__ = ("guild", "event_name", "action")

    def __init__(self, event_name: str, *, member, guild: discord.Guild, moderator, reason, **kwargs):
        self.guild = guild
        self.event_name = event_name
        self.action = Action(self.guild.id, event_name, member, moderator, reason, **kwargs)

    @property
    def member(self):
        """A shortcut for InfractionEvent.action.target"""
        return self.action.target

    @property
    def moderator(self):
        """A shortcut for InfractionEvent.action.moderator"""
        return self.action.moderator

    @property
    def reason(self):
        """A shortcut for InfractionEvent.action.reason"""
        return self.action.reason

    def __str__(self):
        return self.event_name


class GuildConfigInvalidateEvent:
    __slots__ = ("guild")

    def __init__(self, guild):
        self.guild = guild


# lightning_channel_config_remove
class ChannelConfigInvalidateEvent(GuildConfigInvalidateEvent):
    __slots__ = ("channel")

    def __init__(self, channel):
        self.channel = channel
        super().__init__(channel.guild)


# lightning_guild_role_remove
class GuildRoleDeleteEvent(BaseAuditLogEvent):
    __slots__ = ("role")

    def __init__(self, role: discord.Role, entry):
        super().__init__(entry)
        self.role: discord.Role = role

    @property
    def guild(self) -> discord.Guild:
        return self.role.guild

    @property
    def guild_id(self) -> int:
        return self.role.guild.id


# lightning_infraction_update
class InfractionUpdateEvent:
    __slots__ = ("before", "after")

    def __init__(self, before: InfractionRecord, after: InfractionRecord) -> None:
        self.before = before
        self.after = after


# lightning_infraction_delete
class InfractionDeleteEvent:
    __slots__ = ("moderator", "infraction")

    def __init__(self, infraction: InfractionRecord, moderator: discord.Member) -> None:
        self.infraction = infraction
        self.moderator = moderator

    def format_infraction(self) -> discord.Embed:
        infraction = self.infraction

        embed = discord.Embed(title=str(infraction.action).capitalize(),
                              description=infraction.reason or "No reason provided",
                              timestamp=add_tzinfo(infraction.created_at))
        embed.add_field(name="User", value=base_user_format(infraction.user))
        embed.add_field(name="Moderator", value=base_user_format(infraction.moderator))
        embed.add_field(name="Active", value=ticker(infraction.active), inline=False)
        embed.set_footer(text="Infraction created at")

        return embed

# These won't be used yet until I do a refactor of modlogformats for single param events


# lightning_command_ran
class CommandEvent:
    __slots__ = ("command", "user", "ran_at", "channel")

    def __init__(self, ctx):
        self.command = ctx.command.qualified_name
        self.user = ctx.author
        self.ran_at = ctx.message.created_at
        self.channel = ctx.channel  # We can get guild from here...
