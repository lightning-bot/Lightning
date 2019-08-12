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
import config

def get_botmgmt():
    if os.path.isfile(f"config/botmanagers.json"):
        with open(f"config/botmanagers.json", "r") as f:
            return json.load(f)
    else:
        return {"botmanager": []}

def write_botmgmt(contents):
    os.makedirs(f"config", exist_ok=True)
    with open(f"config/botmanagers.json", "w") as f:
        json.dump(contents, f)

def read_bm(uid):
    bm = get_botmgmt()
    uid = str(uid)
    if uid not in bm['botmanager']:
        return False

def add_botmanager(userid):
    uid = str(userid)
    bm = get_botmgmt()
    if uid not in bm['botmanager']:
        bm['botmanager'].append(uid)
    write_botmgmt(bm)

def remove_botmanager(userid):
    uid = str(userid)
    bm = get_botmgmt()
    if uid in bm['botmanager']:
        bm['botmanager'].remove(uid)
    write_botmgmt(bm)

def check_if_botmgmt(ctx):
    if not ctx.guild:
        return False
    bm = get_botmgmt()
    if str(ctx.author.id) in bm['botmanager'] or str(ctx.author.id) == config.owner_id:
        return True