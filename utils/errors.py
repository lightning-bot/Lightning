# Lightning.py - The Successor to Lightning.js
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
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version


# Custom Error Handlers

from discord.ext import commands


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
