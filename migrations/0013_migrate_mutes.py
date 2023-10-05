__name__ = "0013_migrate_mutes"

import json


async def start(conn):
    records = await conn.fetch("SELECT * FROM infractions;")
    for record in records:
        if record['extra'] is None:
            continue

        record = dict(record)
        record['extra'] = json.loads(record['extra'])

        if "timer_id" not in record['extra']:
            continue

        if isinstance(record['extra']['timer_id'], dict):
            old_timer = record['extra'].pop('timer_id')
            record['extra']['timer'] = old_timer['id']
            await conn.execute("UPDATE infractions SET extra=$1 WHERE id=$2 AND guild_id=$3;",
                               json.dumps(record['extra']), record['id'], record['guild_id'])
