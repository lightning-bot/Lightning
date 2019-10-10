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


class Sniped:
    __slots__ = ('guild_id', 'ignored_channels', 'ignored_people')

    def __init__(self, record):
        self.guild_id = record['guild_id']
        self.ignored_channels = record['ignored_channels']
        self.ignored_people = record['ignored_people']

    def is_ignored_channel(self, channel):
        return channel.id in self.ignored_channels


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
