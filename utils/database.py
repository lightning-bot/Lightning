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
    __slots__ = ("mute_role_id", "log_channels", "log_format", "warn_kick", "warn_ban")

    def __init__(self, record):
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
