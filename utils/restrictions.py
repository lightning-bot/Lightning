# MIT License
#
# Copyright (c) 2018 Arda "Ave" Ozkal
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json
import os

def get_restrictions(guild):
    if os.path.isfile(f"config/{guild.id}/restrictions.json"):
        with open(f"config/{guild.id}/restrictions.json", "r") as f:
            return json.load(f)
    else:
        return {}


def set_restrictions(guild, contents):
    os.makedirs(f"config/{guild.id}", exist_ok=True)
    with open(f"config/{guild.id}/restrictions.json", "w") as f:
        json.dump(contents, f)

def get_user_restrictions(guild, uid):
    uid = str(uid)
    with open(f"config/{guild.id}restrictions.json", "r") as f:
        rsts = json.load(f)
        if uid in rsts:
            return rsts[uid]
        return []

def add_restriction(guild, uid, rst):
    # mostly from kurisu source, credits go to ihaveamac
    uid = str(uid)
    rsts = get_restrictions(guild)
    if uid not in rsts:
        rsts[uid] = []
    if rst not in rsts[uid]:
        rsts[uid].append(rst)
    set_restrictions(guild, json.dumps(rsts))


def remove_restriction(guild, uid, rst):
    # mostly from kurisu source, credits go to ihaveamac
    uid = str(uid)
    rsts = get_restrictions(guild)
    if uid not in rsts:
        rsts[uid] = []
    if rst in rsts[uid]:
        rsts[uid].remove(rst)
    set_restrictions(guild, json.dumps(rsts))