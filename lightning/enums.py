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
from discord import Enum
from discord.ext.commands import BadArgument
from flags import Flags

__all__ = ("ConfigFlags",
           "ModFlags",
           "LoggingType",
           "PunishmentType")


class BaseFlags(Flags):
    """Flags subclass that adds a convert function"""
    @classmethod
    async def convert(cls, ctx, argument):
        if argument.lower() in cls.keys():
            return cls[argument]
        else:
            raise BadArgument(f"\"{argument}\" is not a valid feature flag.")


class ConfigFlags(BaseFlags):
    # Deletes invocation messages
    invoke_delete = 1 << 0
    # Reapplies roles to users when they rejoin
    role_reapply = 1 << 1
    # Reapplies punishments only.
    role_reapply_punishments_only = 1 << 2


class ModFlags(BaseFlags):
    # Deletes messages over 2000 characters
    # This probably isn't a "moderation" thing but w/e
    delete_longer_messages = 1 << 0
    # Reacts only when e.g. ban is used
    react_only_confirmation = 1 << 1
    # Hides the confirmation message
    hide_confirmation_message = 1 << 2


class LoggingType(Flags):
    __all_flags_name__ = "all"

    # Bot Event
    COMMAND_RAN = 1 << 0

    # Moderation Events
    MEMBER_KICK = 1 << 1
    MEMBER_BAN = 1 << 2
    MEMBER_MUTE = 1 << 3
    MEMBER_UNMUTE = 1 << 4
    MEMBER_WARN = 1 << 5
    MEMBER_UNBAN = 1 << 6

    # Discord Events
    MEMBER_JOIN = 1 << 7
    MEMBER_LEAVE = 1 << 8
    MEMBER_ROLE_ADD = 1 << 9
    MEMBER_ROLE_REMOVE = 1 << 10
    MEMBER_NICK_CHANGE = 1 << 11
    MEMBER_SCREENING_COMPLETE = 1 << 12

    def __str__(self):
        return self.name


class PunishmentType(Enum):
    DELETE = 1
    WARN = 2
    KICK = 3
    MUTE = 4
    TEMPMUTE = 5
    BAN = 6
    TEMPBAN = 7
