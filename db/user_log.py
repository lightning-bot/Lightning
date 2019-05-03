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

# Changes to this is erasing the mutes
import json
import time
import os
import db.per_guild_config

userlog_event_types = {"warns": "Warn",
                       "bans": "Ban",
                       "kicks": "Kick",
                       "mutes": "Mute",
                       "notes": "Note"
                       }


def get_userlog(guild):
    if os.path.isfile(f"config/{guild.id}/userlog.json"):
        with open(f"config/{guild.id}/userlog.json", "r") as f:
            return json.load(f)
    else:
        return {}


def set_userlog(guild, contents):
    os.makedirs(f"config/{guild.id}", exist_ok=True)
    with open(f"config/{guild.id}/userlog.json", "w") as f:
        json.dump(contents, f)


def userlog(guild, uid, issuer, reason, event_type, uname: str = ""):
        userlogs = get_userlog(guild)
        uid = str(uid)
        if uid not in userlogs:
            userlogs[uid] = {"warns": [],
                             "mutes": [],
                             "kicks": [],
                             "bans": [],
                             "notes": [],
                             "watch": False,
                             "name": "n/a"}
        if uname:
            userlogs[uid]["name"] = uname
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_data = {"issuer_id": issuer.id,
                    "issuer_name": f"{issuer}",
                    "reason": reason,
                    "timestamp": timestamp}
        if event_type not in userlogs[uid]:
            userlogs[uid][event_type] = []
        userlogs[uid][event_type].append(log_data)
        set_userlog(guild, userlogs)
        return len(userlogs[uid][event_type])
