"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

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
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import urllib.parse
from datetime import datetime
from io import BytesIO
from typing import List, Optional

import dateutil.parser
import discord
import feedparser
from discord import app_commands
from discord.ext import commands, menus, tasks
from jishaku.functools import executor_function

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       LightningContext, Storage, command, hybrid_command)
from lightning.cogs.homebrew import ui
from lightning.converters import Whitelisted_URL
from lightning.errors import LightningError
from lightning.utils.checks import hybrid_guild_permissions

log: logging.Logger = logging.getLogger(__name__)

try:
    from wand.image import Image
except ImportError:
    HAS_MAGICK = False
else:
    HAS_MAGICK = True


class UniversalDBPageSource(menus.ListPageSource):
    def __init__(self, entries):
        super().__init__(entries, per_page=1)

    async def format_page(self, menu, entry):
        desc: str = entry['description'] or "No description found..."
        embed = discord.Embed(title=entry['title'], color=discord.Color.blurple(), description=desc)

        if entry['downloads']:
            downloads = [f"[{k}]({v['url']})" for k, v in entry['downloads'].items()]
            joined = "\n".join(downloads)

            if len(joined) > 1024:
                # We might shorten this and throw it on a paste site if we have to.
                embed.description += f"\n\n**Latest Downloads**\n{joined}"
            else:
                embed.add_field(name="Latest Downloads", value=joined)

        # We probably don't have a qr if there's no downloads but whatever
        if entry['qr']:
            embed.set_thumbnail(url=list(entry['qr'].values())[0])

        embed.set_author(name=entry['author'])

        if entry['updated']:
            embed.timestamp = dateutil.parser.parse(entry['updated'])
            embed.set_footer(text="Last updated at")

        if entry['urls']:
            embed.url = entry['urls'][0]

        return embed


async def FindBMPAttachment(ctx: GuildContext):
    async for message in ctx.channel.history(limit=15):
        for attachment in message.attachments:
            if attachment.url and attachment.url.endswith(".bmp"):
                try:
                    return Whitelisted_URL(attachment.url)
                except LightningError:
                    continue
    raise commands.BadArgument('Couldn\'t find an attachment that ends with ".bmp"')


# This isn't a full semantic version regex
SEMANTIC_VERSION_REGEX = r'^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)'


class Homebrew(LightningCog):
    def __init__(self, bot: LightningBot):
        self.bot = bot

        # FAQ
        self.faq_entry_cache = {}

        # Nintendo updates related
        self.ninupdates_data = Storage("resources/nindy_data.json")
        self.ninupdates_feed_digest: Optional[bytes] = None
        self.do_ninupdates.start()

    def cog_unload(self) -> None:
        self.do_ninupdates.stop()

    @command(aliases=['nuf'], level=CommandLevel.Admin, hidden=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    @app_commands.guild_only()
    @hybrid_guild_permissions(manage_webhooks=True)
    async def nintendoupdatealerts(self, ctx: GuildContext) -> None:
        """Manages the server's configuration for Nintendo console update alerts"""
        await ui.NinUpdates(context=ctx).start(wait=False)

    async def check_ninupdate_feed(self):
        feed_url = 'https://yls8.mtheall.com/ninupdates/feed.php'
        # Letting feedparser do the request for us can block the entire bot
        # https://github.com/kurtmckee/feedparser/issues/111
        async with self.bot.aiosession.get(feed_url, expect100=True) as resp:
            raw_bytes = await resp.read()

        # Running feedparser is expensive.
        digest = hashlib.sha256(raw_bytes).digest()
        if self.ninupdates_feed_digest == digest:
            return

        log.debug("Cached digest does not equal the current digest...")
        feed = feedparser.parse(raw_bytes, response_headers={"Content-Location": feed_url})
        self.ninupdates_feed_digest = digest
        for entry in feed["entries"]:
            raw_version = entry["title"].split(" ")[-1]
            match = re.match(SEMANTIC_VERSION_REGEX, raw_version)
            if not match:
                # A date ("2022-04-19_00-05-06") version
                return
            version = match.string
            console = entry["title"].replace(raw_version, " ").strip()
            link = entry["link"]

            if "published" in entry and entry.published:
                timestamp = dateutil.parser.parse(entry.published)
            else:
                continue

            try:
                if timestamp <= datetime.fromtimestamp(self.ninupdates_data[console]['last_updated'],
                                                       tz=timestamp.tzinfo):
                    continue
            except TypeError:
                if timestamp <= datetime.fromisoformat(self.ninupdates_data[console]['last_updated']):
                    continue
            except KeyError:
                pass

            hook_text = f"[{discord.utils.format_dt(timestamp, style='T')}] \N{POLICE CARS REVOLVING LIGHT} **System"\
                        f" update detected for {console}: {version}**\nMore information at <{link}>"
            await self.ninupdates_data.add(console, {"version": version,
                                           "last_updated": timestamp.isoformat()})
            await self.dispatch_message_to_guilds(console, hook_text)

    async def dispatch_message_to_guilds(self, console: str, text: str) -> None:
        records = await self.bot.pool.fetch("SELECT * FROM nin_updates;")
        if not records:
            return

        log.info(f"Dispatching new update message for {console} to {len(records)} guilds.")
        bad_webhooks: List[str] = []  # list of webhook tokens
        for record in records:
            webhook = discord.Webhook.partial(record['id'], record['webhook_token'], session=self.bot.aiosession)
            try:
                await webhook.send(text, avatar_url="https://i.imgur.com/GydiXTi")
            except (discord.Forbidden, discord.NotFound):
                bad_webhooks.append(record['webhook_token'])

        # Remove deleted webhooks if applicable
        if bad_webhooks:
            query = "DELETE FROM nin_updates WHERE webhook_token=$1;"
            await self.bot.pool.executemany(query, [(token,) for token in bad_webhooks])

    @tasks.loop(seconds=45)
    async def do_ninupdates(self) -> None:
        await self.check_ninupdate_feed()

    @do_ninupdates.before_loop
    async def before_ninupdates_task(self) -> None:
        await self.bot.wait_until_ready()

    @executor_function
    def convert_to_png(self, _bytes) -> BytesIO:
        with Image(blob=BytesIO(_bytes)) as img:
            img.format = "jpeg"
            image_bytes = BytesIO()
            img.save(image_bytes)
            image_bytes.seek(0)

        return image_bytes

    @command()
    @commands.cooldown(30, 1, commands.BucketType.user)
    async def bmp(self, ctx: LightningContext,
                  link: Whitelisted_URL = commands.parameter(default=FindBMPAttachment,
                                                             displayed_default="<last bmp image>")) -> None:
        """Converts a .bmp image to .png"""
        img_bytes = await ctx.request(link.url)
        img_final = await self.convert_to_png(img_bytes)
        await ctx.send(file=discord.File(img_final, filename=f"{secrets.token_urlsafe()}.jpeg"))

    @hybrid_command(aliases=['udb'])
    async def universaldb(self, ctx: LightningContext, *, application: str) -> None:
        """Searches for homebrew on Universal-DB"""
        url = f"https://udb-api.celveren.dev/search/{urllib.parse.quote(application)}"
        resp = await ctx.request(url)
        results = resp['results']

        if not results:
            await ctx.send("No results found!")
            return

        menu = ui.UniversalDBPaginator(UniversalDBPageSource(results), context=ctx)
        await menu.start(wait=False)

    @universaldb.autocomplete('application')
    async def universaldb_autocomplete(self, interaction: discord.Interaction, string: str):
        resp = await self.bot.aiosession.get(f"https://udb-api.celveren.dev/search/{urllib.parse.quote(string)}")
        if resp.status != 200:
            return []

        resp = await resp.json()

        if not resp['results']:
            return []

        return [app_commands.Choice(name=app['title'], value=app['title']) for app in resp['results'][:25]]
