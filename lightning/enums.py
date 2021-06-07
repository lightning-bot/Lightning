"""
Lightning.py - A personal Discord bot
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
from discord.ext.commands import BadArgument
from flags import Flags


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
