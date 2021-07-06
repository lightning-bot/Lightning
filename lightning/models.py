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
from datetime import datetime
from typing import Union

import discord

from lightning import errors
from lightning.commands import CommandLevel
from lightning.context import LightningContext
from lightning.enums import ConfigFlags as ConfigBFlags
from lightning.enums import LoggingType, ModFlags, PunishmentType
from lightning.utils import modlogformats
from lightning.utils.time import natural_timedelta, strip_tzinfo

# Alias
ConfigFlags = ConfigBFlags


class GuildModConfig:
    __slots__ = ("guild_id", "mute_role_id", "warn_kick", "warn_ban", "temp_mute_role_id", "flags")

    def __init__(self, record):
        self.guild_id = record['guild_id']
        self.mute_role_id = record['mute_role_id']
        self.warn_kick = record['warn_kick']
        self.warn_ban = record['warn_ban']
        self.temp_mute_role_id = record['temp_mute_role_id']
        self.flags = ModFlags(record['flags'] or 0)
        # self.automod = AutoModConfig(record)
        # self.raid_mode = record['raid_mode']

    def get_mute_role(self, ctx: LightningContext) -> discord.Role:
        if not self.mute_role_id:
            raise errors.MuteRoleError("This server has not setup a mute role")

        role = discord.utils.get(ctx.guild.roles, id=self.mute_role_id)
        if not role:
            raise errors.MuteRoleError('The mute role that was set seems to be deleted.'
                                       ' Please set a new mute role.')
        return role

    def get_temp_mute_role(self, ctx: LightningContext, *, fallback=True) -> discord.Role:
        if not self.temp_mute_role_id and not self.mute_role_id:
            raise errors.MuteRoleError("This server has not setup a mute role.")

        if not self.temp_mute_role_id and fallback is False:
            raise errors.MuteRoleError("This server has not setup a temporary mute role.")

        if not self.temp_mute_role_id:
            return self.get_mute_role(ctx)

        role = discord.utils.get(ctx.guild.roles, id=self.temp_mute_role_id)
        if not role:
            raise errors.MuteRoleError("The temporary mute role that was set seems to be deleted. Please set a new "
                                       "temporary mute role.")

        return role


class AutoModConfig:
    def __init__(self, bot, record):
        self.mention_spam = AutoModMentionConfig(record['automod_mention_spam'])
        self.warnings = AutoModPunishmentConfig()
        self.join_thresholds = AutoModRaidModeConfig()


class AutoModRaidModeConfig:
    def __init__(self, record):
        self.config = AutoModPunishmentConfig(record['punishments_config'])
        # X amount of users can join in Y seconds, if more than act.
        self.users = record['automod_join_threshold_users']
        self.seconds = record['automod_join_threshold_seconds']


class AutoModMentionConfig:
    __slots__ = ("config", "count")

    def __init__(self, record):
        self.config = AutoModPunishmentConfig(record['punishments_config'])  # Punishment config
        self.count = record['count']


class AutoModPunishmentConfig:
    __slots__ = ("punishment_type", "event", "interval")

    def __init__(self, record):
        self.punishment_type = PunishmentType(record['type'])
        self.event = record['event']
        self.interval = record['interval']


class LoggingConfig:
    __slots__ = ('logging')

    def __init__(self, records):
        self.logging = {}
        for record in records:
            self.logging[record['channel_id']] = {"types": LoggingType(record['types']),
                                                  "format": record['format']}

    def get_channels_with_feature(self, feature) -> list:
        channels = []
        for key, value in list(self.logging.items()):
            if feature in value['types']:
                channels.append((key, value))
        return channels

    def get(self, key):
        return self.logging.get(key, None)

    def remove(self, key):
        del self.logging[key]


class CommandOverrides:
    __slots__ = ('overrides')

    def __init__(self, records):
        self.overrides = {}
        for command, record in list(records.items()):
            level = record.get("LEVEL", None)
            overrides = record.get("ID_OVERRIDES", None)
            self.overrides[command] = {"LEVEL": level, "ID_OVERRIDES": overrides}

    def get_overrides(self, command: str):
        return self.overrides.get(command, None)

    def is_command_level_blocked(self, command: str):
        override = self.overrides.get(command, {}).get("LEVEL", None)
        if override is None:
            return False

        if override == CommandLevel.Disabled.value:
            return True

        return False

    def is_command_id_overriden(self, command: str, ids: list):
        override_ids = self.overrides.get(command, {}).get("ID_OVERRIDES", None)
        if override_ids is None:
            return False

        if any(_id in override_ids for _id in ids) is False:
            return False

        return True

    def resolve_overrides(self, ctx: LightningContext) -> bool:
        # TODO: Rewrite this.
        # {"DISABLED": {"COMMANDS": {}, "COGS": {}}}
        # {"PERMISSION_OVERRIDES": {command: {"USERS": [], "ROLES": []}}}
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

    def to_dict(self):
        return self.overrides

    def __getitem__(self, key):
        return self.overrides[key]


class LevelConfig:
    def __init__(self, record):
        self.ADMIN = record.get("ADMIN", []) or []
        self.MOD = record.get("MOD", []) or []
        self.TRUSTED = record.get("TRUSTED", []) or []
        self.BLOCKED = record.get("BLOCKED", []) or []

    def get_user_level(self, user_id: int, role_ids: list) -> CommandLevel:
        ids = [user_id]
        ids.extend(role_ids)
        if any(r for r in ids if r in self.BLOCKED):
            return CommandLevel.Blocked

        if any(r for r in ids if r in self.ADMIN):
            return CommandLevel.Admin

        if any(r for r in ids if r in self.MOD):
            return CommandLevel.Mod

        if any(r for r in ids if r in self.TRUSTED):
            return CommandLevel.Trusted

        return CommandLevel.User

    def to_dict(self):
        return {"ADMIN": self.ADMIN, "MOD": self.MOD, "TRUSTED": self.TRUSTED, "BLOCKED": self.BLOCKED}


class GuildPermissionsConfig:
    def __init__(self, record):
        self.fallback = record.get('fallback', True)
        self.command_overrides = CommandOverrides(record['COMMAND_OVERRIDES']) if "COMMAND_OVERRIDES" in record else \
            None
        self.levels = LevelConfig(record['LEVELS']) if "LEVELS" in record else None
        # self.disabled_features = record['DISABLED']

    def raw(self):
        y = {}

        if self.command_overrides:
            y['COMMAND_OVERRIDES'] = self.command_overrides.to_dict()
        else:
            y['COMMAND_OVERRIDES'] = {}

        if self.levels:
            y['LEVELS'] = self.levels.to_dict()
        else:
            y['LEVELS'] = {}

        return y


class PartialGuild:
    def __init__(self, record):
        self.id = record['id']
        self.name = record['name']
        self.owner_id = record['owner_id']
        self.left_at = record['left_at']


class Timer:
    __slots__ = ('extra', 'event', 'id', 'created_at', 'expiry')

    def __init__(self, id, event, created_at, expiry, extra):
        self.id = id
        self.event = event
        self.created_at = created_at
        self.expiry = expiry
        self.extra = extra

    @classmethod
    def from_record(cls, record):
        return cls(record['id'], record['event'], record['created'], record['expiry'], record['extra'])

    @property
    def created(self):
        return self.created_at

    @property
    def natural_td(self):
        return natural_timedelta(self.created_at, source=self.expiry)

    def __int__(self):
        return self.id


class GuildBotConfig:
    def __init__(self, record):
        self.guild_id = record['guild_id']
        self.toggleroles = record['toggleroles']
        self.prefix = record['prefix']
        self.autorole = record['autorole']
        self.flags = ConfigFlags(record['flags'] or 0)
        self.permissions = GuildPermissionsConfig(record['permissions']) if record['permissions'] is not None else None

    @property
    def prefixes(self):
        return self.prefix


def to_action(value):
    if isinstance(value, modlogformats.ActionType):
        return value

    a = getattr(modlogformats.ActionType, value)
    if not a:
        raise ValueError

    return a


class Action:
    def __init__(self, guild_id: int, action: Union[modlogformats.ActionType, str],
                 target: Union[discord.Member, discord.User, int],
                 moderator: Union[discord.Member, discord.User, int], reason: str = None, *, expiry=None, **kwargs):
        self.guild_id = guild_id
        self.action = to_action(action)
        self.target = target
        self.moderator = moderator
        self.reason = reason
        self.expiry = expiry
        self.kwargs = kwargs
        self.timestamp = self.kwargs.pop("timestamp", datetime.utcnow())

        self.infraction_id = None

    async def add_infraction(self, connection) -> int:
        """Inserts an infraction into the database.

        As a safeguard, timestamp and expiry datetimes are stripped of tzinfo"""
        if len(self.kwargs) == 0:
            query = """INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at, expiry)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)
                       RETURNING id;"""
            r = await connection.fetchval(query, self.guild_id, self.target.id, self.moderator.id, self.action.value,
                                          self.reason, strip_tzinfo(self.timestamp), strip_tzinfo(self.expiry))
        else:
            query = """INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at, expiry, extra)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                       RETURNING id;"""
            r = await connection.fetchval(query, self.guild_id, self.target.id, self.moderator.id, self.action.value,
                                          self.reason, strip_tzinfo(self.timestamp), strip_tzinfo(self.expiry),
                                          self.kwargs)

        self.infraction_id = r
        return r

    def is_logged(self):
        return bool(self.infraction_id)

    @property
    def event(self):
        return self.action.upper()
