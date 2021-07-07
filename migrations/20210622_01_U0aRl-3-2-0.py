"""
3.2.0
"""

from yoyo import step

from lightning.enums import LoggingType

__depends__ = {'20210128_01_dkC4d-3-0-0-migration', '20210609_01_YXSjP-3-2-0'}


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


def apply(conn):
    cur = conn.cursor()
    # Temp column
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


steps = [
    step(apply)
]
