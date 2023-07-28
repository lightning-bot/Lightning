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

import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import discord

from lightning import errors
from lightning.commands import CommandLevel
from lightning.constants import AUTOMOD_EVENT_NAMES_LITERAL
from lightning.context import LightningContext
from lightning.enums import ActionType, AutoModPunishmentType, LoggingType
from lightning.utils.time import strip_tzinfo

if TYPE_CHECKING:
    from lightning import LightningBot


class GuildModConfig:
    __slots__ = ("guild_id", "mute_role_id", "warn_kick", "warn_ban",
                 "bot", "message_report_channel_id")

    def __init__(self, record, bot):
        self.guild_id: int = record['guild_id']
        self.mute_role_id: Optional[int] = record['mute_role_id']
        self.warn_kick: Optional[int] = record['warn_kick']
        self.warn_ban: Optional[int] = record['warn_ban']
        self.bot: LightningBot = bot
        # Adding message report config to here for now. It might evolve as time goes on.
        self.message_report_channel_id: Optional[int] = record['message_report_channel_id']

    def get_mute_role(self) -> discord.Role:
        if not self.mute_role_id:
            raise errors.MuteRoleError("This server has not setup a mute role")

        # Configurations get invalidated if the bot leaves so this should never be None
        guild = self.bot.get_guild(self.guild_id)

        role = guild.get_role(self.mute_role_id)
        if not role:
            raise errors.MuteRoleError('The mute role that was set seems to be deleted.'
                                       ' Please set a new mute role.')
        return role

    def get_message_report_channel(self) -> Optional[discord.TextChannel]:
        guild = self.bot.get_guild(self.guild_id)
        return guild.get_channel(self.message_report_channel_id)


class LoggingConfig:
    __slots__ = ('logging')

    def __init__(self, records):
        self.logging = {}
        for record in records:
            self.logging[record['channel_id']] = {"types": LoggingType(record['types']),
                                                  "format": record['format'],
                                                  "webhook_url": record['webhook_url']}

    def get_channels_with_feature(self, log_type: int) -> List[Tuple[int, Dict[str, Any]]]:
        channels = []
        for key, value in list(self.logging.items()):
            if log_type in value['types']:
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

    def get_overrides(self, command: str) -> Optional[dict]:
        """Gets overrides for a command

        command : str
            The command to get overrides for"""
        return self.overrides.get(command, None)

    def is_command_level_blocked(self, command: str) -> bool:
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
        admin = record.pop("ADMIN", {})
        self.admin_role_ids = admin.pop("ROLE_IDS", [])
        self.admin_user_ids = admin.pop("USER_IDS", [])
        self.admin_ids = [*self.admin_role_ids, *self.admin_user_ids]

        mod = record.pop("MOD", {})
        self.mod_role_ids = mod.pop("ROLE_IDS", [])
        self.mod_user_ids = mod.pop("USER_IDS", [])
        self.mod_ids = [*self.mod_role_ids, *self.mod_user_ids]

        trusted = record.pop("TRUSTED", {})
        self.trusted_role_ids = trusted.pop("ROLE_IDS", [])
        self.trusted_user_ids = trusted.pop("USER_IDS", [])
        self.trusted_ids = [*self.trusted_role_ids, *self.trusted_user_ids]

        blocked = record.pop("BLOCKED", {})
        self.blocked_role_ids = blocked.pop("ROLE_IDS", [])
        self.blocked_user_ids = blocked.pop("USER_IDS", [])
        self.blocked_ids = [*self.blocked_role_ids, *self.blocked_user_ids]

        # Legacy attributes
        self.ADMIN = self.admin_ids
        self.MOD = self.mod_ids
        self.TRUSTED = self.trusted_ids
        self.BLOCKED = self.blocked_ids

    def get_user_level(self, user_id: int, role_ids: list) -> CommandLevel:
        ids = [user_id, *role_ids]
        if any(r for r in ids if r in self.blocked_ids):
            return CommandLevel.Blocked

        if any(r for r in ids if r in self.admin_ids):
            return CommandLevel.Admin

        if any(r for r in ids if r in self.mod_ids):
            return CommandLevel.Mod

        if any(r for r in ids if r in self.trusted_ids):
            return CommandLevel.Trusted

        return CommandLevel.User

    def blame(self, user_id: int, role_ids: list) -> Optional[str]:
        """Figures out how a user is a certain level."""
        ids = [user_id, *role_ids]
        roles = [*self.blocked_role_ids, *self.admin_role_ids, *self.mod_role_ids, *self.trusted_role_ids]
        if any(r for r in ids if r in roles):
            return "roles"

        users = [*self.blocked_user_ids, *self.admin_user_ids, *self.mod_user_ids, *self.trusted_user_ids]
        if any(r for r in ids if r in users):
            return "users"

        return None

    def to_dict(self):
        return {"ADMIN": {"ROLE_IDS": self.admin_role_ids, "USER_IDS": self.admin_user_ids},
                "MOD": {"ROLE_IDS": self.mod_role_ids, "USER_IDS": self.mod_user_ids},
                "TRUSTED": {"ROLE_IDS": self.trusted_role_ids, "USER_IDS": self.trusted_user_ids},
                "BLOCKED": {"ROLE_IDS": self.blocked_role_ids, "USER_IDS": self.blocked_user_ids}}


class GuildPermissionsConfig:
    __slots__ = ('fallback', 'command_overrides', 'levels')

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
    __slots__ = ('id', 'name', 'owner_id', 'left_at')

    def __init__(self, record):
        self.id = record['id']
        self.name = record['name']
        self.owner_id = record['owner_id']
        self.left_at = record['left_at']


class Timer:
    __slots__ = ('extra', 'event', 'id', 'created_at', 'expiry', 'timezone')

    def __init__(self, id: int, event: str, created_at: datetime.datetime, expiry: datetime.datetime, timezone: str,
                 extra: Optional[Dict[str, Any]]):
        self.id = id
        self.event = event
        self.created_at = created_at
        self.expiry = expiry
        self.extra = extra
        self.timezone: str = timezone

    @classmethod
    def from_record(cls, record: dict):
        return cls(record['id'],
                   record['event'],
                   record['created'],
                   record['expiry'],
                   record['timezone'],
                   record['extra'])

    def __int__(self):
        return self.id


class GuildBotConfig:
    __slots__ = ('bot', 'guild_id', 'toggleroles', 'prefixes', 'autorole_id', 'permissions')

    def __init__(self, bot: LightningBot, record):
        self.bot: LightningBot = bot

        self.guild_id: int = record['guild_id']
        self.toggleroles: Optional[List[int]] = record['toggleroles']
        self.prefixes: Optional[List[str]] = record['prefixes']
        self.autorole_id: Optional[int] = record['autorole']

        if record['permissions']:
            self.permissions = GuildPermissionsConfig(record['permissions'])
        else:
            self.permissions = None

    @property
    def autorole(self) -> Optional[discord.Role]:
        guild = self.bot.get_guild(self.guild_id)
        return guild.get_role(self.autorole_id) if guild else None


def to_action(value):
    if isinstance(value, ActionType):
        return value

    a = getattr(ActionType, value)
    if not a:
        raise ValueError

    return a


class Action:
    def __init__(self, guild_id: int, action: Union[ActionType, str],
                 target: Union[discord.Member, discord.User, int],
                 moderator: Union[discord.Member, discord.User, int], reason: Optional[str] = None, *,
                 expiry: Optional[datetime.datetime] = None, **kwargs):
        self.guild_id = guild_id
        self.action: ActionType = to_action(action)
        self.target = target
        self.moderator = moderator
        self.reason = reason
        self.expiry = expiry
        self.kwargs = kwargs
        self.timestamp: datetime.datetime = self.kwargs.pop("timestamp", discord.utils.utcnow())

        self.infraction_id: Optional[int] = None

    async def add_infraction(self, connection) -> int:
        """Inserts an infraction into the database.

        As a safeguard, timestamp and expiry datetimes are stripped of tzinfo"""
        if self.expiry:
            expiry = strip_tzinfo(self.expiry)
        else:
            expiry = None

        if len(self.kwargs) == 0:
            query = """INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at, expiry)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)
                       RETURNING id;"""
            r = await connection.fetchval(query, self.guild_id, self.target.id, self.moderator.id, self.action.value,
                                          self.reason, strip_tzinfo(self.timestamp), expiry)
        else:
            query = """INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at, expiry,
                                                extra)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                       RETURNING id;"""
            r = await connection.fetchval(query, self.guild_id, self.target.id, self.moderator.id, self.action.value,
                                          self.reason, strip_tzinfo(self.timestamp), expiry, self.kwargs)

        self.infraction_id = r
        return r

    def is_logged(self) -> bool:
        return bool(self.infraction_id)

    @property
    def event(self) -> str:
        return self.action.upper()


class GuildAutoModRulePunishment:
    def __init__(self, record) -> None:
        self.type = AutoModPunishmentType[record['type']]
        self.duration: Optional[str] = record.get('duration', None)


class GuildAutoModRule:
    def __init__(self, record) -> None:
        self.id: int = record['id']
        self.guild_id: int = record['guild_id']
        self.type: AUTOMOD_EVENT_NAMES_LITERAL = record['type']
        self.count: int = record['count']
        self.seconds: int = record['seconds']
        self.ignores: List[int] = record['ignores']
        self.punishment = GuildAutoModRulePunishment(record['punishment'])


class InfractionRecord:
    def __init__(self, bot: LightningBot, record: Dict[str, Any]):
        self.id: int = record['id']

        self.guild = bot.get_guild(record['guild_id']) or record['guild_id']
        self.user = bot.get_user(record['user_id']) or record['user_id']
        self.moderator = bot.get_user(record['moderator_id']) or record['user_id']

        self.action = ActionType(record['action'])
        self.reason: str = record['reason']
        self.created_at = datetime.datetime.fromisoformat(record['created_at'])
        self.active: bool = record['active']
        self.extra: dict[str, Any] = record['extra']

    @property
    def guild_id(self) -> int:
        return self.guild.id if hasattr(self.guild, 'id') else self.guild

    @property
    def user_id(self) -> int:
        return self.user.id if hasattr(self.user, 'id') else self.user

    @property
    def moderator_id(self) -> int:
        return self.moderator.id if hasattr(self.moderator, 'id') else self.moderator
