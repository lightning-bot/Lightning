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

from typing import Any, Dict, Optional

from lightning.storage import TOMLStorage


def transform_key(key, *, default=None):
    return default if key == "" else key


class Config(TOMLStorage):
    def __init__(self, file_path: str = 'config.toml'):
        super().__init__(file_path)
        self._set_attrs()

    async def save(self) -> None:
        await super().save()
        self._set_attrs()

    def _set_attrs(self):
        self.bot = BotConfig(self._storage['bot'])
        self.tokens = TokensConfig(self._storage['tokens'])
        self.logging = LoggingConfig(self._storage['logging'])


class TokensConfig:
    __slots__ = ('discord', 'sentry', 'postgres', 'redis', 'api', 'prometheus', 'dbots', 'topgg')

    def __init__(self, data: Dict[str, Any]) -> None:
        self.discord: str = data['discord']
        self.sentry: Optional[str] = transform_key(data['sentry'])
        self.postgres = PostgresConfig(data['postgres'])
        self.redis = RedisConfig(data['redis'])
        self.api = SanctumConfig(data['api'])
        self.prometheus = PrometheusConfig(data['prometheus'])
        # Bot listings
        self.dbots: Optional[str] = transform_key(data.pop('dbots', ""))
        self.topgg: Optional[str] = transform_key(data.pop('topgg', ""))


class PostgresConfig:
    __slots__ = ('uri',)

    def __init__(self, data: Dict[str, Any]) -> None:
        self.uri: str = data['uri']


class RedisConfig:
    __slots__ = ('host', 'port', 'password', 'db')

    def __init__(self, data: Dict[str, Any]) -> None:
        self.host = data['host']
        self.port = transform_key(data.pop('port', None))
        self.password = transform_key(data.pop("password", None))
        self.db = data['db']


class SanctumConfig:
    __slots__ = ("url", "key")

    def __init__(self, data: Dict[str, Any]) -> None:
        self.url = data['url']
        self.key = data['key']


class PrometheusConfig:
    __slots__ = ("port",)

    def __init__(self, data: Dict[str, Any]) -> None:
        self.port: int = data.pop('port', 8050)


class LoggingConfig:
    __slots__ = ('bot_errors', 'guild_alerts', 'blacklist_alerts', 'console')

    def __init__(self, data: Dict[str, Any]) -> None:
        self.bot_errors = data['bot_errors']
        self.guild_alerts = data['guild_alerts']
        self.blacklist_alerts = data['blacklist_alerts']
        self.console = data['console']


class BotConfig:
    __slots__ = ('description', 'spam_count', 'game', 'edit_commands', 'support_server_invite', 'git_repo',
                 'user_agent', 'beta_prefix', 'disabled_cogs', 'message_cache_max', 'owner_ids')

    def __init__(self, data: Dict[str, Any]) -> None:
        self.description = data.pop("description", None)
        self.spam_count = data['spam_count']
        self.game = data.pop("game", None)
        self.edit_commands = data.pop('edit_commands', False)
        self.support_server_invite = data.pop('support_server_invite', None)
        self.git_repo = data.pop('git_repo', 'https://github.com/lightning-bot/Lightning')
        self.user_agent = transform_key(data.pop('user_agent', None))
        self.beta_prefix = data.pop('beta_prefix', None)
        self.disabled_cogs = data.pop('disabled_cogs', [])
        self.message_cache_max = data.pop('message_cache_max', 1000)
        self.owner_ids = data.pop('owner_ids', None)
