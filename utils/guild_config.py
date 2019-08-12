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


import dataset

DB_URL = dataset.connect("sqlite:///config/guild_config.sqlite3")

def write_to_guild_config(guid: int, column: str, input):
    """Example function for guild config"""
    res = DB_URL['config'].find_one(guild_id=guid)
    if res is None:
        DB_URL['config'].insert(dict(guild_id=guid, column=input))
    else:
        DB_URL['config'].update(dict(guild_id=guid, column=input), ['guild_id'])

def remove_from_guild_config(guid: int, column: str):
    """Another Example Function"""
    try:
        res = DB_URL['config'].find(guild_id=guid)
        for config in res:
            DB_URL['config'].delete(column=config[f'{column}'])
    except:
        return False

def read_guild_config(guid: int, column: str):
    res = DB_URL['config'].find_one(guild_id=guid)
    if res is None:
        return False
    try:
        return res[f'{column}']
    except KeyError:
        return False
