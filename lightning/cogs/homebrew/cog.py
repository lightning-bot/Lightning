"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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
from typing import List, Optional, Union

import asyncpg
import dateutil.parser
import discord
import feedparser
from bs4 import BeautifulSoup
from discord import app_commands
from discord.ext import commands, menus, tasks
from jishaku.functools import executor_function
from rapidfuzz import fuzz, process

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       LightningContext, Storage, command, group,
                       hybrid_command)
from lightning.cogs.homebrew import ui
from lightning.converters import Whitelisted_URL
from lightning.errors import LightningError
from lightning.utils.checks import has_channel_permissions
from lightning.utils.helpers import request as make_request

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
        desc: str = entry['description'] if 'description' in entry else "No description found..."
        embed = discord.Embed(title=entry['title'], color=discord.Color.blurple(), description=desc)

        if 'downloads' in entry:
            downloads = [f"[{k}]({v['url']})" for k, v in entry['downloads'].items()]
            joined = "\n".join(downloads)

            if len(joined) > 1024:
                # We might shorten this and throw it on a paste site if we have to.
                embed.description += f"\n\n**Latest Downloads**\n{joined}"
            else:
                embed.add_field(name="Latest Downloads", value=joined)

        # We probably don't have a qr if there's no downloads but whatever
        if 'qr' in entry:
            embed.set_thumbnail(url=list(entry['qr'].values())[0])

        embed.set_author(name=entry['author'])

        if 'updated' in entry:
            embed.timestamp = dateutil.parser.parse(entry['updated'])
            embed.set_footer(text="Last updated at")

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


FAQ_MAPPING = {"twilightmenu": "https://wiki.ds-homebrew.com/twilightmenu/faq",
               "twlmenu": "https://wiki.ds-homebrew.com/twilightmenu/faq",
               "nds-bootstrap": "https://wiki.ds-homebrew.com/nds-bootstrap/faq",
               "gbarunner2": "https://wiki.ds-homebrew.com/gbarunner2/faq"}


def mod_embed(title: str, description: str, social_links: List[str], color: Union[int, discord.Color],
              *, separator="\N{BULLET}") -> discord.Embed:
    """Creates an embed for console modding information

    Parameters
    ----------
    title : str
        The title for the embed
    description : str
        The description for the embed
    social_links : list
        A list of social links
    color : Union[int, discord.Color]
        A color hex
    separator : str, Optional
        Separator for social_links

    Returns
    -------
    :class:discord.Embed
        Returns the created embed
    """
    em = discord.Embed(title=title, description=description, color=color)
    links = f'\n{separator} '.join(social_links)
    em.add_field(name="Social Links", value=f'{separator} {links}')
    return em


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

    @group(aliases=['nuf', 'stability'], invoke_without_command=True, level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_webhooks=True)
    @has_channel_permissions(manage_webhooks=True)
    async def nintendoupdatesfeed(self, ctx: GuildContext) -> None:
        """Manages the guild's configuration for Nintendo console update alerts.

        If invoked with no subcommands, this will start an interactive menu."""
        await ui.NinUpdates(context=ctx).start(wait=False)

    @nintendoupdatesfeed.command(name="setup", level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_webhooks=True)
    @has_channel_permissions(manage_webhooks=True)
    async def nuf_configure(self, ctx: GuildContext, *,
                            channel: discord.TextChannel = commands.CurrentChannel) -> None:
        """Sets up a webhook in the specified channel that will send Nintendo console updates."""
        record = await self.bot.pool.fetchval("SELECT id FROM nin_updates WHERE guild_id=$1", ctx.guild.id)
        if record:
            await ctx.send("This server has already configured Nintendo console updates!")
            return

        try:
            webhook = await channel.create_webhook(name="Nintendo Console Updates")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to create webhook. `{e}`")
            return

        query = """INSERT INTO nin_updates (guild_id, id, webhook_token)
                   VALUES ($1, $2, $3);"""
        try:
            await self.bot.pool.execute(query, ctx.guild.id, webhook.id, webhook.token)
        except asyncpg.UniqueViolationError:
            await ctx.send("This server has already configured Nintendo console updates!")
        else:
            await ctx.send(f"Successfully created webhook in {channel.mention}")

    @nintendoupdatesfeed.command(name="delete", level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_webhooks=True)
    @has_channel_permissions(manage_webhooks=True)
    async def nuf_delete(self, ctx: GuildContext) -> None:
        """Deletes the configuration of Nintendo console updates."""
        record = await self.bot.pool.fetchrow("SELECT * FROM nin_updates WHERE guild_id=$1", ctx.guild.id)
        if record is None:
            await ctx.send("Nintendo console updates are currently not configured!")
            return

        webhook = discord.utils.get(await ctx.guild.webhooks(), id=record['id'])
        query = 'DELETE FROM nin_updates WHERE guild_id=$1;'

        if webhook is None:
            await self.bot.pool.execute(query, ctx.guild.id)
            await ctx.send("Successfully deleted configuration!")
            return

        await webhook.delete()
        await self.bot.pool.execute(query, ctx.guild.id)
        await ctx.send("Successfully deleted webhook and configuration!")

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

    async def science_xml(self, raw):
        ch = self.bot.get_channel(1054808921879101511)
        if not ch:
            ch = await self.bot.fetch_channel(1054808921879101511)

        await ch.send("Uploaded feed", file=discord.File(BytesIO(raw), "feed.xml"))

    async def dispatch_message_to_guilds(self, console: str, text: str) -> None:
        records = await self.bot.pool.fetch("SELECT * FROM nin_updates;")
        if not records:
            return

        log.info(f"Dispatching new update message for {console} to {len(records)} guilds.")
        bad_webhooks: List[str] = []  # list of webhook tokens
        for record in records:
            webhook = discord.Webhook.partial(record['id'], record['webhook_token'])
            try:
                await webhook.send(text)
            except discord.Forbidden or discord.NotFound:
                bad_webhooks.append(record['webhook_token'])

        # Remove deleted webhooks if applicable
        if bad_webhooks:
            query = "DELETE FROM nin_updates WHERE webhook_token=$1;"
            await self.bot.pool.executemany(query, bad_webhooks)

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
        url = f"https://udb-api.lightsage.dev/search/{urllib.parse.quote(application)}"
        resp = await ctx.request(url)
        results = resp['results']

        if not results:
            await ctx.send("No results found!")
            return

        menu = ui.UniversalDBPaginator(UniversalDBPageSource(results), context=ctx)
        await menu.start(wait=False)

    @universaldb.autocomplete('application')
    async def universaldb_autocomplete(self, interaction: discord.Interaction, string: str):
        resp = await self.bot.aiosession.get(f"https://udb-api.lightsage.dev/search/{urllib.parse.quote(string)}")
        if resp.status != 200:
            return []

        resp = await resp.json()

        if not resp['results']:
            return []

        return [app_commands.Choice(name=app['title'], value=app['title']) for app in resp['results'][:25]]

    @group(invoke_without_command=True)
    async def mod(self, ctx: LightningContext) -> None:
        """Gets console modding information"""
        await ctx.send_help('mod')

    def get_match(self, word_list: list, word: str, score_cutoff: int = 60, partial=False) -> Optional[str]:
        if partial:
            result = process.extractOne(word, word_list, scorer=fuzz.partial_ratio,
                                        score_cutoff=score_cutoff)
        else:
            result = process.extractOne(word, word_list, scorer=fuzz.ratio,
                                        score_cutoff=score_cutoff)
        if not result:
            return None
        return result

    def get_faq_entries_from(self, content):
        entries = []
        soup = BeautifulSoup(content, 'lxml')
        divs = soup.find_all('div', id="faq-container")
        for div in divs:
            for entry in div.find_all("details", class_="accordian-item"):
                title = entry.find("summary")
                d = entry.find("div")
                param = f"?faq={entry['id'][4:]}"
                entries.append((title.string.strip(), d.text.strip(), param))
        return entries

    async def fetch_faq_entries(self, site):
        raw = await make_request(site, self.bot.aiosession)
        entries = {
            tup[0]: {"description": tup[1], "link": f"{site}{tup[2]}"}
            for tup in self.get_faq_entries_from(raw)
        }

        self.faq_entry_cache[site] = entries
        return self.faq_entry_cache[site]

    async def get_faq_entry(self, site, content):
        if site not in self.faq_entry_cache:
            entries = await self.fetch_faq_entries(site)
        else:
            entries = self.faq_entry_cache[site]

        match = self.get_match(list(entries.keys()), content, 40)  # 40 should be safe cutoff
        if not match:
            return None

        return (match[0], entries[match[0]])

    @mod.command(name='faq')
    async def mod_faq(self, ctx: LightningContext, entity: str, *, question: str) -> None:
        """Shows a faq entry for an entity.

        Valid entities are "twilightmenu", "nds-bootstrap", or "gbarunner2".
        """
        match = self.get_match(list(FAQ_MAPPING.keys()), entity, 50)
        if not match:
            await ctx.send(f"Failed to convert entity parameter. Please see `{ctx.clean_prefix}help mod faq`")
            return

        entity = FAQ_MAPPING[match[0]]

        entry = await self.get_faq_entry(entity, question)
        if not entry:
            await ctx.send(entity)
            return

        title, entry = entry
        await ctx.send(f"**{title}**\n> <{entry['link']}>\n{entry['description']}")

    @mod.command(name="3ds", aliases=['3d', '3DS', '2DS', '2ds'])
    async def mod_3ds(self, ctx: LightningContext) -> None:
        """Gives information on 3DS modding."""
        featurelist = ["Redirect your NAND to the SD card",
                       "Run any software compatible, regardless "
                       "of if Nintendo signed it or if it was made for your region",
                       "Run game backups without requiring a physical cartridge",
                       "Redirect Software Data to the SD card, used for software modification",
                       "Customize your HOME Menu with user-created themes",
                       "Experience software the way you'd like it with screenshots and cheat codes",
                       "Backup, edit, and restore save data",
                       "Play older software using their respective emulator",
                       "Stream live gameplay to your PC wirelessly "
                       "with NTR CFW (requires a New system)"]

        em = discord.Embed(title="Nintendo 3DS Modding guide",
                           url="https://3ds.hacks.guide",
                           color=0x49151)
        em.description = ("This [guide](https://3ds.hacks.guide) will install "
                          "LumaCFW alongside boot9strap, the latest CFW")
        features = '\n- '.join(featurelist)
        em.add_field(name="Advantages to modding a 3DS", value=f"- {features}")
        em.set_footer(text='Guide by Plailect',
                      icon_url='https://pbs.twimg.com/profile_images/698944593715310592/'
                      'wTDlD5rA_400x400.png')
        await ctx.send(embed=em)

    @mod.group(name="ds", aliases=['dsi'], invoke_without_command=True,
               case_insensitive=False)
    async def mod_ds(self, ctx: LightningContext) -> None:
        """Gives information on DS modding"""
        features = ["Run Nintendo DS game backups natively on your DSi SD card without the need of a flashcard.",
                    "Use normally incompatible flashcards",
                    "Boot into different homebrew applications by holding different buttons when turning on your "
                    "Nintendo DSi.",
                    "Launch any DSiWare (out-of-region & 3DS exclusives) from your SD card",
                    "Display an image (referred to as the boot splash) on system launch",
                    "Watch your favorite movies using FastVideoDS",
                    "Run old-time classics using a variety of emulators"]
        em = discord.Embed(title="Nintendo DSi Modding guide",
                           url="https://dsi.cfw.guide/",
                           color=0xD6FEFF)
        em.description = ("This [guide](https://dsi.cfw.guide/) "
                          "will take you from a regular Nintendo "
                          "DSi to a modified console by using the Memory Pit exploit."
                          "\n(If looking for Flashcard usage, use `mod ds flashcard`)")
        feature = '\n- '.join(features)
        em.add_field(name="Advantages to modding a Nintendo DSi", value=f"- {feature}")
        em.set_footer(text="Guide by NightScript, RocketRobz & emiyl")
        await ctx.send(embed=em)

    @mod_ds.command(name='flashcard', aliases=['flashcart'])
    async def mod_ds_flashcard(self, ctx: LightningContext) -> None:
        features = ["Run Nintendo DS game backups without requiring "
                    "a physical cartridge",
                    "Load multiple backups of Nintendo DS games "
                    "without having to carry around a bunch of cartridges",
                    "Modify your Nintendo DS game using Cheat Codes",
                    "Install Custom FirmWare on your 3DS using NTRBoot Hax"]
        embed = discord.Embed(title="Nintendo DS Flashcard guide",
                              url="https://www.reddit.com/r/flashcarts/wiki/ds-quick-start-guide",
                              color=0xD6FEFF)
        embed.description = ("This [guide](https://www.reddit.com/r/flashcarts/wiki/ds-quick-start-guide)"
                             " links to most flashcard kernels that are made "
                             "for the Nintendo DS. You can also view its "
                             "compatibility status for the Nintendo DSi and the Nintendo 3DS")
        feature = '\n- '.join(features)
        embed.add_field(name="Advantages to using a Flashcard", value=f"- {feature}")
        embed.set_footer(text="Guide by NightScript",
                         icon_url="https://btw.i-use-ar.ch/i/pglx.png")
        await ctx.send(embed=embed)

    @mod.command(name='switch', aliases=['nx'])
    async def mod_switch_guide(self, ctx: LightningContext) -> None:
        """Gives information on Switch modding"""
        em = discord.Embed(title="Nintendo Switch Modding guide",
                           url="https://nh-server.github.io/switch-guide/",
                           color=0x00FF11)
        em.description = ("This [guide](https://nh-server.github.io/switch-guide) "
                          "will install Atmosphère, the latest and safest CFW.")
        features = ["Customize your HOME Menu with user-created themes and "
                    "splash screens",
                    "Use “ROM hacks” for games that you own",
                    "Backup, edit, and restore saves for applications",
                    "Play games for older systems with various emulators"
                    ", using RetroArch or other standalone emulators"]
        featuresformat = '\n\U00002022 '.join(features)
        em.add_field(name="Advantages to modding a Nintendo Switch",
                     value=f"\U00002022 {featuresformat}")
        em.set_footer(text="Guide made by the Nintendo Homebrew Discord Server")
        await ctx.send(embed=em)

    @mod.command(name='wii')
    async def mod_wii(self, ctx: LightningContext) -> None:
        """Gives information on Nintendo Wii modding"""
        em = discord.Embed(title="Nintendo Wii Modding guide",
                           url="https://wii.guide/",
                           color=0x00FF11)
        em.description = ("This [guide](https://wii.guide/) will install the Homebrew Channel, "
                          "the one channel for all things homebrew.")
        features = ["Patch game disc contents (allowing you to load game modifications) using Riivolution.",
                    "Install themes to your Wii Menu using MyMenuify.",
                    "Install a USB Loader like WiiFlow Lite or USB Loader GX "
                    "to launch all your favorite titles from a USB storage device and more.",
                    "Back up your discs with CleanRip and installed games and titles with YABDM.",
                    "Back up and restore your save files with SaveGame Manager GX",
                    "Download new homebrew apps with the Homebrew Browser",
                    "Restore discontinued online services, such as WiiConnect24 & Nintendo WFC services.",
                    "Backup and restore copies of your Wii system memory (NAND) using BootMii.",
                    "Protect your Wii from bricks using Priiloader and BootMii.",
                    "Turn your Wii into a media player with WiiMC."]
        featuresformat = '\n\U00002022 '.join(features)
        em.add_field(name="Advantages to modding a Nintendo Wii",
                     value=f"\U00002022 {featuresformat}")
        em.set_footer(text="Guide made by the RiiConnect24 team and others")
        await ctx.send(embed=em)
