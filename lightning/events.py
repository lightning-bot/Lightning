"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

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
from lightning.models import Action

# These are event models that'll be passed for listeners cog


class BaseAuditLogEvent:
    __slots__ = ("moderator", "reason")

    def __init__(self, entry=None):
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

    def __init__(self, before, after, entry):
        super().__init__(entry)
        self.before = before
        self.after = after
        self.entry = entry

    @property
    def guild(self):
        """A shortcut for MemberUpdateEvent.after.guild"""
        return self.after.guild


# lightning_member_role_change
class MemberRolesUpdateEvent(MemberUpdateEvent):
    @property
    def added_roles(self):
        added = [role for role in self.after.roles if role not in self.before.roles]
        return added

    @property
    def removed_roles(self):
        removed = [role for role in self.before.roles if role not in self.after.roles]
        return removed


# lightning_member_role_add
# lightning_member_role_remove
class MemberRoleUpdateEvent(BaseAuditLogEvent):
    __slots__ = ("role")

    def __init__(self, role, entry):
        super().__init__(entry)
        self.role = role


# lightning_member_kick
# lightning_member_ban
# lightning_member_unban
class AuditLogModAction(BaseAuditLogEvent):
    """Represents a moderation event that was taken from Audit Logs

    This will also build the Action class from the parameters given."""
    __slots__ = ("member", "guild", "action")

    def __init__(self, event, member, entry, *, guild=None):
        super().__init__(entry)
        self.member = member

        if guild:
            self.guild = guild
        else:
            self.guild = member.guild  # An "alias" for Action.guild_id. At some point, we'll change Action.

        self.action = Action(self.guild.id, event, member, self.moderator, self.reason)

# lightning_member_mute
# lightning_member_unmute
# lightning_member_kick
# lightning_member_ban
# lightning_member_unban


class InfractionEvent:  # ModerationEvent sounded nice too...
    __slots__ = ("guild", "event_name", "action")

    def __init__(self, event_name: str, *, member, guild, moderator, reason, **kwargs):
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

# These won't be used yet until I do a refactor of modlogformats for single param events


# lightning_command_ran
class CommandEvent:
    __slots__ = ("command", "user", "ran_at", "channel")

    def __init__(self, ctx):
        self.command = ctx.command.qualified_name
        self.user = ctx.author
        self.ran_at = ctx.message.created_at
        self.channel = ctx.channel  # We can get guild from here...
