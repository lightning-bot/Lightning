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
    with open(f"config/{guild.id}/prefixes.json", "r") as f:
        rst = json.load(f)
        if "prefixes" in rst:
            return rst["prefixes"]
        return False

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