# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2019 - LightSage
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
import time
import json


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

        publish_time = time.mktime(entry["published_parsed"])
        if publish_time <= data[console]["lastupdate"]:
            continue

        data[console] = {"version": version,
                         "lastupdate": publish_time}

        hook_text = f"🚨 **System update detected for {console}: {version}**\n"\
                    f"More information at <{link}>\n"
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
