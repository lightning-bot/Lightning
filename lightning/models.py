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

import discord

from lightning import LightningContext, errors
from lightning.enums import Levels


class GuildModConfig:
    __slots__ = ("guild_id", "mute_role_id", "warn_kick", "warn_ban", "temp_mute_role_id", "logging", "logged_features")

    def __init__(self, record):
        self.guild_id = record['guild_id']
        self.mute_role_id = record['mute_role_id']
        self.warn_kick = record['warn_kick']
        self.warn_ban = record['warn_ban']
        self.temp_mute_role_id = record['temp_mute_role_id']

    def mute_role(self, ctx: LightningContext):
        if self.mute_role_id:
            role = discord.utils.get(ctx.guild.roles, id=self.mute_role_id)
            if role:
                return role
            else:
                raise errors.LightningError('The mute role that was set seems to be deleted.'
                                            ' Please set a new mute role.')
        else:
            return None


class Logging:
    __slots__ = ('channel_id', 'types', 'format')

    def __init__(self, record):
        self.channel_id = record['channel_id']
        self.types = record['types']
        self.format = record['format']


class CommandOverrides:
    __slots__ = ('overrides')

    def __init__(self, records):
        self.overrides = {}
        for record in records:
            level = record['level']
            overrides = record.get('id_overrides', None)
            self.overrides[record['command']] = {"LEVEL": level,
                                                 "OVERRIDES": overrides}

    def is_command_level_blocked(self, command: str):
        override = self.overrides.get(command, {}).get("LEVEL", None)
        if override is None:
            return False

        if override == Levels.Blocked.value:
            return True

        return False

    def is_command_id_overriden(self, command: str, ids: list):
        override_ids = self.overrides.get(command, {}).get("OVERRIDES", None)
        if override_ids is None:
            return False

        if any(_id in override_ids for _id in ids) is False:
            return False

        return True

    def resolve_overrides(self, ctx: LightningContext) -> bool:
        command = ctx.command.qualified_name
        ids = [r.id for r in ctx.author.roles]
        ids.append(ctx.author.id)
        if self.is_command_id_overriden(command, ids) is True:
            # User has explicit permission to use this command
            return True

        # Check if level is blocked
        if self.is_command_level_blocked(command) is True:
            # blocked commmand...
            return False

        return True

    def __getitem__(self, key):
        return self.overrides[key]
