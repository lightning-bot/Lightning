import json
import os

def get_botmgmt():
    if os.path.isfile(f"config/botmanagers.json"):
        with open(f"config/botmanagers.json", "r") as f:
            return json.load(f)
    else:
        return {}

def write_botmgmt(contents):
    os.makedirs(f"config", exist_ok=True)
    with open(f"config/botmanagers.json", "w") as f:
        json.dump(contents, f)

def read_bm(uid):
    bm = get_botmgmt()
    uid = int(uid)
    if uid not in bm:
        return False
    return True

def check_if_botmgmt(ctx):
    if not ctx.guild:
        return False
    bm = get_botmgmt()
    uid = int(ctx.author.id)
    if uid not in bm:
        return False
    return True