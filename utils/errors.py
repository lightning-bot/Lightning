# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2019 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Custom Error Handlers

from discord.ext import commands
from resources import botemojis


class LightningError(commands.CommandError):
    """Base class for custom errors"""
    pass


class TimersUnavailable(LightningError):
    def __init__(self):
        super().__init__("Lightning\'s timer system is currently unavailable. "
                         "Please try again later.")


class BadTarget(LightningError):
    pass


class NoImageProvided(LightningError):
    def __init__(self):
        super().__init__("Please provide an image.")


class ChannelNotFound(LightningError):
    def __init__(self, channel):
        super().__init__(f"Channel {channel} not found.")


class ChannelPermissionFailure(LightningError):
    pass


class MessageNotFoundInChannel(LightningError):
    def __init__(self, message_id, channel):
        super().__init__(f"Message ({message_id}) was not found in {channel.mention}.")


class NotOwnerorBotManager(LightningError):
    def __init__(self):
        super().__init__("This command is restricted to my bot manager(s) and owner.")


class MuteRoleError(LightningError):
    pass


class MissingStaffRole(LightningError):
    def __init__(self, staffrole):
        super().__init__(f"None of your roles indicate you are a {staffrole}.")


class MissingRequiredPerms(LightningError):
    def __init__(self, permission):
        super().__init__(f"{botemojis.x} You are missing required "
                         f"permission(s) `{', '.join(permission)}`!")


class NoWarns(LightningError):
    def __init__(self, user):
        super().__init__(f"<@{user}> has no warns.")


class WarnError(LightningError):
    pass
