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
import json

import discord

from utils.errors import LightningError


class Sniped:
    __slots__ = ('guild_id', 'ignored_channels', 'ignored_people')

    def __init__(self, record):
        self.guild_id = record['guild_id']
        self.ignored_channels = record['ignored_channels']
        self.ignored_people = record['ignored_people']

    def is_ignored_channel(self, channel):
        return channel.id in self.ignored_channels


class GuildModConfig:
    __slots__ = ("guild_id", "mute_role_id", "log_channels", "log_format", "warn_kick", "warn_ban")

    def __init__(self, record):
        # self.bot = bot # LOL
        self.guild_id = record['guild_id']
        self.mute_role_id = record['mute_role_id']
        self.log_channels = record['log_channels']
        self.log_format = record['log_format']
        self.warn_kick = record['warn_kick']
        self.warn_ban = record['warn_ban']

    def mute_role(self, ctx):
        if self.mute_role_id:
            ret = discord.utils.get(ctx.guild.roles, id=self.mute_role_id)
            if ret:
                return ret
            else:
                raise LightningError('The mute role that was set seems to be deleted.'
                                     ' Please set a new mute role.')
        else:
            return None

    def has_log_channel(self, key: str):
        """Checks if the log channel exists,
        if so returns the channel id and log format"""
        if not self.log_channels:
            return None
        ext = json.loads(self.log_channels)
        if key in ext:
            return ext[key], self.log_format if self.log_format else "kurisu"
        else:
            return None

    def __repr__(self):
        return f"<GuildModConfig guild_id={self.guild_id} mute_role_id={self.mute_role_id}"\
               f" log_channels={self.log_channels} log_format={self.log_format} warn_kick="\
               f"{self.warn_kick} warn_ban={self.warn_ban}>"


class DatabaseUpdate:
    """Class to assist with database updates
    without needing to run the schema over again"""
    snipe = """CREATE TABLE IF NOT EXISTS sniped_messages
(
    guild_id BIGINT,
    channel_id BIGINT PRIMARY KEY,
    message VARCHAR(2000),
    user_id BIGINT,
    timestamp TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS snipe_settings
(
    guild_id BIGINT PRIMARY KEY,
    channel_ids BIGINT [],
    user_ids BIGINT []
);
                """
    console_updates = """CREATE TABLE IF NOT EXISTS nin_updates
(
    guild_id BIGINT PRIMARY KEY,
    id BIGINT,
    webhook_token VARCHAR (500)
);"""
    ooftoggle = """CREATE TABLE IF NOT EXISTS ooftoggle
(
    guild_id BIGINT PRIMARY KEY
);"""
    logformat = """ALTER TABLE guild_mod_config ADD COLUMN log_format SMALLINT;"""
    warnings = """CREATE TABLE IF NOT EXISTS warns
(
    guild_id BIGINT NOT NULL,
    warn_id SERIAL,
    user_id BIGINT,
    mod_id BIGINT,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
    reason TEXT,
    pardoned BOOLEAN DEFAULT FALSE,
    CONSTRAINT warns_pkey PRIMARY KEY (guild_id, warn_id)
);

CREATE TABLE IF NOT EXISTS pardoned_warns
(
    guild_id BIGINT,
    warn_id SERIAL,
    mod_id BIGINT,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
    FOREIGN KEY (guild_id, warn_id) REFERENCES warns (guild_id, warn_id) ON DELETE CASCADE,
    CONSTRAINT pardoned_warns_pkey PRIMARY KEY (guild_id, warn_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS warns_uniq_idx ON warns (warn_id, user_id, mod_id, timestamp, reason, pardoned);
CREATE UNIQUE INDEX IF NOT EXISTS pardoned_warns_uniq_idx ON pardoned_warns (warn_id, mod_id, timestamp);"""
