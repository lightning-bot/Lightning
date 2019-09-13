# kirigiri - A discord bot.
# Copyright (C) 2018 - Valentijn "noirscape" V.
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
# In addition, the additional clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version; or

import discord
import os
import json


class FakeGuild:
    """
    Pseudo class with only an ID attribute.

    Use this if you only have the ID of the guild.
    """

    def __init__(self, guildid):
        self.id = guildid


def write_guild_config(guild: discord.Guild, config: dict, filename: str):
    """Dumps a json config for a guild.

    Parameters:
        guild: The guild this config is for.
        config: Config data, should be a dict.
        filename: filename to write to, should be unique. (.json is appended automatically)"""
    os.makedirs(f"config/{guild.id}", exist_ok=True)
    with open(f"config/{guild.id}/{filename}.json", "w") as outfile:
        json.dump(config, outfile)


def get_guild_config(guild: discord.Guild, filename: str) -> dict:
    """Gets a json config for a guild.

    Parameters:
        guild: The guild whose config should be retrieved.
        filename: filename to get. (.json is appended automatically)

    Returns:
        dict: Dictionary containing config data.
    """
    os.makedirs(f"config/{guild.id}", exist_ok=True)
    with open(f"config/{guild.id}/{filename}.json", "r") as configfile:
        return json.load(configfile)


def exist_guild_config(guild: discord.Guild, filename: str) -> bool:
    """Checks if guild has a json config

    Parameters:
        guild: The guild which should be checked. (.json is appended automatically)
        filename: filename to check for.

    Returns:
        bool: True if config exists, False if it doesn't."""
    return os.path.isfile(f"config/{guild.id}/{filename}.json")
