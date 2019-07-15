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

def check_if_botmgmt(ctx):
    if not ctx.guild:
        return False
    bm = get_botmgmt()
    if str(ctx.author.id) in bm['botmanager'] or str(ctx.author.id) == config.owner_id:
        return True