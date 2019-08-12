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
import os

def get_prefixes(guild):
    if os.path.isfile(f"config/{guild.id}/prefixes.json"):
        with open(f"config/{guild.id}/prefixes.json", "r") as f:
            return json.load(f)
    else:
        return {}

def set_prefixes(guild, contents):
    os.makedirs(f"config/{guild.id}", exist_ok=True)
    with open(f"config/{guild.id}/prefixes.json", "w") as f:
        json.dump(contents, f)

def get_guild_prefixes(guild):
    rst = get_prefixes(guild)
    if "prefixes" in rst:
        return rst["prefixes"]
    return {}

def add_prefix(guild, prefix):
    px = str(prefix)
    rst = get_prefixes(guild)
    if "prefixes" not in rst:
        rst["prefixes"] = []
    if px not in rst["prefixes"]:
        rst["prefixes"].append(px)
    set_prefixes(guild, rst)

def remove_prefix(guild, prefix):
    px = str(prefix)
    rsts = get_prefixes(guild)
    if "prefixes" not in rsts:
        rsts["prefixes"] = []
    if px in rsts["prefixes"]:
        rsts["prefixes"].remove(px)
    set_prefixes(guild, rsts)