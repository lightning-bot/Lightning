# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2020 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import feedparser
import discord
from datetime import datetime
import json
import dateutil.parser


def json_dump(filename, content):
    with open(filename, "w") as f:
        json.dump(content, f)


def json_load(filename):
    with open(filename, "r") as f:
        return json.load(f)


consoles = {"Old3DS", "Switch", "New3DS", "WiiU"}


async def nintendo_updates_feed(bot):
    data = json_load("stabilite/data.json")
    feed = feedparser.parse('https://yls8.mtheall.com/ninupdates/feed.php')

    for entry in feed["entries"]:
        # Kinda based of stabilite, but also not :peposhrug:
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
            if timestamp <= datetime.fromtimestamp(data[console]["lastupdate"],
                                                   tz=timestamp.tzinfo):
                continue
        except TypeError:
            if timestamp <= datetime.fromisoformat(data[console]['lastupdate']):
                continue

        data[console] = {"version": version,
                         "lastupdate": timestamp.isoformat()}

        hook_text = f"🚨 **System update detected for {console}: {version}**\n"\
                    f"More information at <{link}>"
        query = "SELECT * FROM nin_updates"  # WHERE console=$1"
        ret = await bot.db.fetch(query)
        adp = discord.AsyncWebhookAdapter(bot.aiosession)
        bad_webhooks = []
        for web in ret:
            try:
                webhook_url = webhook_url_builder(web[1], web[2])
                webhook = discord.Webhook.from_url(webhook_url, adapter=adp)
                await webhook.send(hook_text)
            except (discord.NotFound, discord.Forbidden):
                bad_webhooks.append(web[1])
            except discord.HTTPException:
                pass
        if bad_webhooks:
            for h in bad_webhooks:
                query = "DELETE FROM nin_updates WHERE id=$1"
                await bot.db.execute(query, h)

    # Save new data to the json
    json_dump("stabilite/data.json", data)


def webhook_url_builder(id, token):
    return f"https://discordapp.com/api/webhooks/{id}/{token}"
