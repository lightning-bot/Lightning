"""
3.2.0 data migrator
"""

import json

from yoyo import step

from lightning.enums import LoggingType

__depends__ = {'20210128_01_dkC4d-initial', '20210609_01_YXSjP-3-2-0'}


flags = {"BAN": "MEMBER_BAN",
         "KICK": "MEMBER_KICK",
         "WARN": "MEMBER_WARN",
         "MUTE": "MEMBER_MUTE",
         "UNMUTE": "MEMBER_UNMUTE",
         "UNBAN": "MEMBER_UNBAN",
         "COMMAND_COMPLETE": "COMMAND_RAN",
         "MEMBER_ROLE_CHANGE": "MEMBER_ROLE_ADD|MEMBER_ROLE_REMOVE"}


def convert_to_flags(record):
    types = record[2]
    assert type(types) == list
    x = []

    for t in types:
        if t in flags:
            x.append(flags[t])
        else:
            x.append(t)

    return LoggingType.from_simple_str("|".join(x))


def migrate_permissions(r: dict) -> str:
    levels = r.get("LEVELS", None)
    if not levels:
        return r

    for key, value in levels.items():
        r["LEVELS"][key] = {"USER_IDS": value}

    return json.dumps(r)


def apply(conn):
    # Logging Changes
    cur = conn.cursor()
    cur.execute("ALTER TABLE logging ADD COLUMN flags INT")
    conn.commit()
    cur.execute("SELECT guild_id, channel_id, types FROM logging")
    records = cur.fetchall()
    recs = [(int(convert_to_flags(record)), record[1]) for record in records]
    cur.executemany("UPDATE logging SET flags=%s WHERE channel_id=%s", recs)

    cur.execute("ALTER TABLE logging DROP COLUMN types")
    cur.execute("ALTER TABLE logging RENAME COLUMN flags TO types;")
    conn.commit()
    cur.close()
    # Permission changes
    cur = conn.cursor()
    cur.execute("SELECT guild_id, permissions FROM guild_config WHERE permissions IS NOT NULL")
    records = cur.fetchall()
    for record in records:
        perms = migrate_permissions(record[1])
        cur.execute("UPDATE guild_config SET permissions=%s WHERE guild_id=%s", (perms, record[0]))
    conn.commit()
    cur.close()


steps = [
    step(apply)
]
