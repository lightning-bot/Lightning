"""
Lightning.py - A multi-purpose Discord bot
Copyright (C) 2020 - LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import io
import logging
from datetime import datetime

import dateutil.parser
import discord
import feedparser

from lightning import LightningBot
from lightning.config import Storage

log = logging.getLogger(__name__)
consoles = {"Old3DS", "Switch", "New3DS", "WiiU"}


async def do_nintendo_updates_feed(bot: LightningBot):
    if not hasattr(bot, 'nintendo_updates'):
        bot.nintendo_updates = Storage("resources/nindy_data.json")

    data = bot.nintendo_updates
    feedurl = 'https://yls8.mtheall.com/ninupdates/feed.php'
    # Letting feedparser do the request for us can block the entire bot
    # https://github.com/kurtmckee/feedparser/issues/111
    async with bot.aiosession.get(feedurl, expect100=True) as resp:
        text = await resp.text()
    feed = feedparser.parse(io.BytesIO(text.encode("UTF-8")), response_headers={"Content-Location": feedurl})

    for entry in feed["entries"]:
        # Kinda based of stabilite
        version = entry["title"].split(" ")[-1]
        console = entry["title"].replace(version, " ").strip()
        link = entry["link"]

        if "published" in entry and entry.published:
            timestamp = dateutil.parser.parse(entry.published)
        elif "updated" in entry:
            timestamp = dateutil.parser.parse(entry.updated)
        else:
            continue

        try:
            # Migration things:tm:
            if timestamp <= datetime.fromtimestamp(data[console]["last_updated"],
                                                   tz=timestamp.tzinfo):
                continue
        except TypeError:
            if timestamp <= datetime.fromisoformat(data[console]['last_updated']):
                continue
        except KeyError:
            pass

        hook_text = f"`[{timestamp.strftime('%H:%M:%S')}]` 🚨 **System update detected for {console}: {version}**\n"\
                    f"More information at <{link}>"
        await data.add(console, {"version": version,
                                 "last_updated": timestamp.isoformat()})
        await dispatch_message(bot, console, hook_text)


async def dispatch_message(bot: LightningBot, console: str, text: str):
    query = "SELECT * FROM nin_updates;"
    records = await bot.pool.fetch(query)
    log.info(f"Dispatching new update for {console} to {len(records)} servers.")
    bad_webhooks = []
    for record in records:
        try:
            webhook_url = webhook_url_builder(record['id'], record['webhook_token'])
            webhook = discord.Webhook.from_url(webhook_url, adapter=discord.AsyncWebhookAdapter(bot.aiosession))
            await webhook.send(text)
        except (discord.NotFound, discord.Forbidden):
            bad_webhooks.append(record['id'])
        except discord.HTTPException:
            # discord heckin died
            continue
    # Remove deleted webhooks
    if bad_webhooks:
        query = "DELETE FROM nin_updates WHERE id=$1;"
        await bot.pool.executemany(query, bad_webhooks)


def webhook_url_builder(webhook_id, token):
    return f"https://discord.com/api/webhooks/{webhook_id}/{token}"
