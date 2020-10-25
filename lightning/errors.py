"""
Lightning.py - A multi-purpose Discord bot
Copyright (C) 2020 - LightSage

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

# Custom Error Handlers
import aiohttp
from discord.ext import commands


class LightningError(commands.CommandError):
    """Base class for custom errors"""


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


class NoWarns(LightningError):
    def __init__(self, user):
        super().__init__(f"<@{user}> has no warns.")


class WarnError(LightningError):
    pass


class EmojiError(LightningError):
    pass


class CogNotAvailable(LightningError):
    def __init__(self, cog):
        super().__init__(f"{cog} is not available.")


class HTTPException(LightningError):
    def __init__(self, response: aiohttp.ClientResponse):
        self.status = response.status
        self.reason = response.reason
        super().__init__(f"HTTP Error {self.status}")


class HTTPRatelimited(HTTPException):
    pass


class HierarchyException(LightningError):
    def __init__(self, thing):
        super().__init__(f"{thing} is higher than your highest {thing}")


class FlagError(Exception):
    """Base error class for flag errors"""


class FlagInputError(FlagError, commands.UserInputError):
    """Base class for input errors relating to flags"""


class MissingRequiredFlagArgument(FlagInputError):
    def __init__(self, missing_flag):
        super().__init__(f"Missing required argument for flag \"{missing_flag}\"")
