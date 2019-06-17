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