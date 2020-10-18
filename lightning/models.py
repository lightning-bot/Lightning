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

from lightning import errors
from lightning.commands import CommandLevel
from lightning.context import LightningContext
from lightning.utils.time import natural_timedelta


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

        if override == CommandLevel.Blocked.value:
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


class GuildPermissions:
    __slots__ = ('admin_ids', 'mod_ids', 'trusted_ids', 'blocked_ids', 'fallback_to_discord_perms')

    def __init__(self, record):
        self.admin_ids = record['admin_ids'] or []
        self.mod_ids = record['mod_ids'] or []
        self.trusted_ids = record['trusted_ids'] or []
        self.blocked_ids = record['blocked_ids'] or []
        self.fallback_to_discord_perms = record['fallback_to_dperms'] or True

    def get_user_level(self, user_id: int, role_ids: list) -> CommandLevel:
        ids = [user_id]
        ids.extend(role_ids)
        if any(r for r in ids if r in self.blocked_ids):
            return CommandLevel.Blocked

        if any(r for r in ids if r in self.admin_ids):
            return CommandLevel.Admin

        if any(r for r in ids if r in self.mod_ids):
            return CommandLevel.Mod

        if any(r for r in ids if r in self.trusted_ids):
            return CommandLevel.Trusted

        return CommandLevel.User


class PartialGuild:
    def __init__(self, record):
        self.id = record['id']
        self.name = record['name']
        self.owner_id = record['owner_id']
        self.left_at = record['left_at']


class Timer:
    __slots__ = ('extra', 'event', 'id', 'created_at', 'expiry')

    def __init__(self, record):
        self.id = record['id']
        self.extra = record['extra']
        self.event = record['event']
        self.created_at = record['created']
        self.expiry = record['expiry']

    @property
    def created(self):
        return self.created_at

    @property
    def natural_td(self):
        return natural_timedelta(self.created_at, source=self.expiry)

    def __int__(self):
        return self.id

    def __repr__(self):
        return f"<Timer id={self.id} event={self.event} created_at={self.created_at}>"
