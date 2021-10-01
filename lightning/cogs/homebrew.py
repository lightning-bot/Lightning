"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

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
import asyncio
import hashlib
import logging
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
from discord.ext import commands, menus, tasks
from jishaku.functools import executor_function
from PIL import Image
from rapidfuzz import fuzz, process

from lightning import (CommandLevel, LightningBot, LightningCog,
                       LightningContext, Storage, command, group)
from lightning.converters import Whitelisted_URL
from lightning.errors import LightningError
from lightning.utils.checks import has_channel_permissions
from lightning.utils.helpers import request as make_request
from lightning.utils.paginator import InfoMenuPages
from lightning.views import homebrew_uis

log: logging.Logger = logging.getLogger(__name__)
SERVICES_CHANNEL = 893508863712690207


class TinyDBPageSource(menus.ListPageSource):
    def __init__(self, entries):
        super().__init__(entries, per_page=1)

    async def format_page(self, menu, entry):
        embed = discord.Embed(title=entry['name'], color=discord.Color.blurple(), description=entry['description'])
        embed.add_field(name="Latest Release",
                        value=f"**Name**: {entry['latestRelease']['name']}\n"
                              f"**Link**: [{entry['latestRelease']['3ds_release_files'][0]['download_url']}]"
                              f"({entry['latestRelease']['3ds_release_files'][0]['download_url']})")
        embed.set_author(name=entry['github_owner'])
        embed.set_image(url=f"https://api.homebrew.space/qr/{entry['id']}")
        return embed


class UniversalDBPageSource(TinyDBPageSource):
    async def format_page(self, menu, entry):
        embed = discord.Embed(title=entry['title'], color=discord.Color.blurple(), description=entry['description'])

        if 'downloads' in entry:
            downloads = [f"[{k}]({v['url']})" for k, v in entry['downloads'].items()]
            embed.add_field(name="Latest Downloads", value="\n".join(downloads))
        # We probably don't have a qr if there's no downloads but whatever
        if 'qr' in entry:
            embed.set_image(url=list(entry['qr'].values())[0])

        embed.set_author(name=entry['author'])
        return embed


class FindBMPAttachment(commands.CustomDefault):
    async def default(self, ctx, param) -> str:
        limit = 15
        async for message in ctx.channel.history(limit=limit):
            for attachment in message.attachments:
                if attachment.url:
                    if attachment.url.endswith(".bmp"):
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


class Homebrew(LightningCog):
    def __init__(self, bot: LightningBot):
        self.bot = bot

        # FAQ
        self.faq_entry_cache = {}

        # Nintendo updates related
        self.ninupdates_data = Storage("resources/nindy_data.json")
        self.ninupdates_feed_digest = None
        self.do_ninupdates.start()

        # UDB-API
        self.ping_task.start()
        self._api_error_dispatched = False

    def cog_unload(self) -> None:
        self.do_ninupdates.cancel()
        self.ping_task.cancel()

    @group(aliases=['nuf', 'stability'], invoke_without_command=True, level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_webhooks=True)
    @has_channel_permissions(manage_webhooks=True)
    async def nintendoupdatesfeed(self, ctx: LightningContext) -> None:
        """Manages the guild's configuration for Nintendo console update alerts.

        If invoked with no subcommands, this will start an interactive menu."""
        await homebrew_uis.NinUpdates().start(ctx)

    @nintendoupdatesfeed.command(name="setup", level=CommandLevel.Admin)
    @commands.bot_has_permissions(manage_webhooks=True)
    @has_channel_permissions(manage_webhooks=True)
    async def nuf_configure(self, ctx: LightningContext, *,
                            channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
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
    async def nuf_delete(self, ctx: LightningContext) -> None:
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
        data = self.ninupdates_data
        feedurl = 'https://yls8.mtheall.com/ninupdates/feed.php'
        # Letting feedparser do the request for us can block the entire bot
        # https://github.com/kurtmckee/feedparser/issues/111
        async with self.bot.aiosession.get(feedurl, expect100=True) as resp:
            raw_bytes = await resp.read()

        # Running feedparser is expensive.
        digest = hashlib.sha256(raw_bytes).digest()
        if self.ninupdates_feed_digest == digest:
            return

        log.debug("Cached digest does not equal the current digest...")
        feed = feedparser.parse(raw_bytes, response_headers={"Content-Location": feedurl})
        self.feed_digest = digest
        for entry in feed["entries"]:
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

            hook_text = f"[{discord.utils.format_dt(timestamp, style='T')}] \N{POLICE CARS REVOLVING LIGHT} **System"\
                        f" update detected for {console}: {version}**\nMore information at <{link}>"
            await data.add(console, {"version": version,
                                     "last_updated": timestamp.isoformat()})
            await self.dispatch_message_to_guilds(console, hook_text)

    async def dispatch_message_to_guilds(self, console: str, text: str) -> None:
        records = await self.bot.pool.fetch("SELECT * FROM nin_updates;")
        log.info(f"Dispatching new update message for {console} to {len(records)} guilds.")
        bad_webhooks = []
        for record in records:
            try:
                webhook = discord.Webhook.partial(record['id'], record['webhook_token'], session=self.bot.aiosession)
                await webhook.send(text)
            except (discord.NotFound, discord.Forbidden):
                bad_webhooks.append(record['id'])
            except discord.HTTPException:  # discord heckin died
                continue

        # Remove deleted webhooks
        if bad_webhooks:
            query = "DELETE FROM nin_updates WHERE id=$1;"
            await self.bot.pool.executemany(query, bad_webhooks)

    @tasks.loop(seconds=45)
    async def do_ninupdates(self) -> None:
        await self.check_ninupdate_feed()

    @do_ninupdates.before_loop
    async def before_ninupdates_task(self) -> None:
        await self.bot.wait_until_ready()

    @executor_function
    def convert_to_png(self, _bytes) -> BytesIO:
        image_b = Image.open(BytesIO(_bytes))
        image_file = BytesIO()
        image_b.save(image_file, format="png")
        image_file.seek(0)
        return image_file

    @command()
    @commands.cooldown(30.0, 1, commands.BucketType.user)
    async def bmp(self, ctx: LightningContext, link: Whitelisted_URL = FindBMPAttachment) -> None:
        """Converts a .bmp image to .png"""
        img_bytes = await ctx.request(link.url)
        img_final = await self.convert_to_png(img_bytes)
        await ctx.send(file=discord.File(img_final, filename=f"{secrets.token_urlsafe()}.png"))

    @command()
    @commands.cooldown(1, 5.0, commands.BucketType.member)
    async def tinydb(self, ctx: LightningContext, *, search: str) -> None:
        """Searches for 3DS homebrew on tinydb"""
        if len(search) <= 3:
            raise LightningError("Search term cannot be 3 characters or less!")
        if len(search) >= 50:
            raise LightningError("Search term cannot be 50 characters or more!")

        url = f"https://api.homebrew.space/search/{urllib.parse.quote(search)}"
        async with self.bot.aiosession.get(url, timeout=30.0) as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                raise LightningError("Tinydb api not available. Try again later?")

        if not data:
            raise LightningError("Failed to find that search term!")

        menu = InfoMenuPages(source=TinyDBPageSource(data), clear_reactions_after=True)
        await menu.start(ctx)

    @command(aliases=['udb'])
    async def universaldb(self, ctx: LightningContext, *, application: str) -> None:
        resp = await ctx.request(f"https://udb-api.lightsage.dev/search/{urllib.parse.quote(application)}")
        results = resp['results']

        if not results:
            await ctx.send("No results found!")
            return

        menu = InfoMenuPages(source=UniversalDBPageSource(results), clear_reactions_after=True)
        await menu.start(ctx)

    @tasks.loop(seconds=60.0)
    async def ping_task(self) -> None:
        try:
            await make_request("https://udb-api.lightsage.dev/stats", self.bot.aiosession)
        except Exception as e:
            # We only need one warning message
            if self._api_error_dispatched:
                return

            channel = self.bot.get_channel(SERVICES_CHANNEL)
            await channel.send(f"\N{WARNING SIGN} Got `{e.status}` with reason `{e.reason}` while trying to ping "
                               "UDB-API.")
            self._api_error_dispatched = True
        else:
            # we recovered
            if self._api_error_dispatched:
                self._api_error_dispatched = False
                channel = self.bot.get_channel(SERVICES_CHANNEL)
                await channel.send("\N{PARTY POPPER} UDB-API has recovered!")

    @ping_task.before_loop
    async def before_ping_task(self):
        await self.bot.wait_until_ready()

    @tinydb.error
    async def tiny_db_error(self, ctx, error) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(str(error))
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(str(error))
        elif isinstance(error, LightningError):
            await ctx.send(str(error))

        if isinstance(error, commands.CommandInvokeError):
            if isinstance(error.original, asyncio.TimeoutError):
                return await ctx.send('Timed out while making the request.')
            await self.bot.log_command_error(ctx, error)

    @group(invoke_without_command=True)
    async def mod(self, ctx: LightningContext) -> None:
        """Gets console modding information


        If any information provided in the commands is incorrect,
        please make an issue on the GitLab repository.
        (https://gitlab.com/lightning-bot/Lightning)"""
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
        entries = {}
        for tup in self.get_faq_entries_from(raw):
            entries[tup[0]] = {"description": tup[1], "link": f"{site}{tup[2]}"}
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

    @mod.group(name="3ds", aliases=['3d', '3DS', '2DS', '2ds'], invoke_without_command=True)
    async def mod_3ds(self, ctx: LightningContext, *, homebrew=None) -> None:
        """Gives information on 3DS modding."""
        if homebrew:
            commands = list(self.mod_3ds.all_commands.keys())
            match = self.get_match(commands, homebrew, 75)
            if match is not None:
                # log.info(f"Command match found {match}")
                await ctx.invoke(self.mod_3ds.get_command(match[0]))
                return

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

    @mod_3ds.command(name='universal-updater', aliases=['uu', 'universalupdater'])
    async def mod_3ds_uu(self, ctx: LightningContext) -> None:
        """Gives information about Universal Updater"""
        social_links = ["[Github Repository](https://github.com/Universal-Team/Universal-Updater)",
                        "[Discord Server](https://discord.gg/KDJCfGF)"]
        description = "A 3DS homebrew that allows easy installation and updating of other 3DS homebrew"
        em = mod_embed("Universal-Updater", description, social_links, discord.Color.green())
        em.set_thumbnail(url="https://btw.i-use-ar.ch/i/7rj8.png")
        em.set_footer(text="Made by Universal-Team")
        await ctx.send(embed=em)

    @mod.group(name="ds", aliases=['dsi'], invoke_without_command=True,
               case_insensitive=False)
    async def mod_ds(self, ctx: LightningContext, *, homebrew=None) -> None:
        """Gives information on DS modding"""
        if homebrew:
            commands = list(self.mod_ds.all_commands.keys())
            match = self.get_match(commands, homebrew, 75)
            if match is not None:
                # log.debug(f"Command match found {match}")
                await ctx.invoke(self.mod_ds.get_command(match[0]))
                return

        features = ["Redirect your NAND to the SD card",
                    "Use normally incompatible flashcards",
                    "Boot into different homebrew applications by holding different buttons when turning on your "
                    "Nintendo DSi.",
                    "Launch any DSiWare (out-of-region & 3DS exclusives) from your SD card",
                    "Run Nintendo DS game backups natively on your DSi SD card without the need of a flashcard.",
                    "Watch your favorite movies using MPEG4Player",
                    "Run old-time favorites using a variety of emulators",
                    "Use FreeNAND to transfer configurations, sys, titles and tickets to another Nintendo DSi from a SD"
                    " NAND"]
        em = discord.Embed(title="Nintendo DSi Modding guide",
                           url="https://dsi.cfw.guide/",
                           color=0xD6FEFF)
        # Original embed color was "16776918", search got me "D6FEFF".
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
                              url="https://nightyoshi370.github.io/mm-github-pages-starter/",
                              color=0xD6FEFF)
        embed.description = ("This [guide](https://nightyoshi370.github.io/mm-github-pages-starter/)"
                             " links to most flashcard kernels that are made "
                             "for the Nintendo DS. You can also view its "
                             "compatibility status for the Nintendo DSi and the Nintendo 3DS")
        feature = '\n- '.join(features)
        embed.add_field(name="Advantages to using a Flashcard", value=f"- {feature}")
        embed.set_footer(text="Guide by NightScript",
                         icon_url="https://btw.i-use-ar.ch/i/pglx.png")
        await ctx.send(embed=embed)

    @mod_ds.command(name='lolsnes')
    async def mod_ds_lolsnes(self, ctx: LightningContext) -> None:
        description = "An open-source Super Nintendo "\
                      "Entertainment System (SNES for short) "\
                      "emulator made for the Nintendo DS using a flashcard."
        links = ["[Website](http://lolsnes.kuribo64.net/)",
                 "[Github Repository](https://github.com/Arisotura/lolSnes)"]
        em = mod_embed("lolSnes", description, links, 0xF8E800)
        em.set_thumbnail(url="https://btw.i-use-ar.ch/i/ed1q.png")
        em.set_footer(text="Made by Arisotura",
                      icon_url="https://btw.i-use-ar.ch/i/yo0w.png")
        await ctx.send(embed=em)

    @mod_ds.command(name="nds-bootstrap", aliases=['ndsbp'])
    async def mod_ds_nds_bootstrap(self, ctx: LightningContext) -> None:
        """Gives information on nds-bootstrap"""
        description = "An open-source application that allows Nintendo DS"\
                      "/DSi ROMs and homebrew to be natively utilised "\
                      "rather than using an emulator. nds-bootstrap works "\
                      "on Nintendo DSi/3DS SD cards through CFW and on "\
                      "Nintendo DS through flashcarts."
        links = ["[GBATemp Thread](https://gbatemp.net/threads/nds-"
                 "bootstrap-loader-run-commercial-nds-backups-from-an-sd-card.454323/)",
                 "[Discord Server](https://discord.gg/yqSut8c)",
                 "[Github Repository](https://github.com/ahezard/nds-bootstrap)"]
        em = mod_embed("nds-bootstrap", description, links, 0x999A9D)
        em.set_thumbnail(url="https://btw.i-use-ar.ch/i/uroq.png")
        em.set_footer(text="Made by ahezard", icon_url="https://btw.i-use-ar.ch/i/0983.png")
        await ctx.send(embed=em)

    @mod_ds.command(name="nesDS")
    async def mod_ds_nesds(self, ctx: LightningContext) -> None:
        """Gives information on nesDS"""
        description = "An open-source Nintendo Entertainment "\
                      "System (NES for short) emulator for a Nintendo "\
                      "DS flashcard or a DSi/3DS SD card."
        links = ["[Github Repository](https://github.com/RocketRobz/NesDS)",
                 "([DSi Edition](https://github.com/ApacheThunder/NesDS))"]
        em = mod_embed("nesDS", description, links, discord.Color.red())
        em.set_footer(text="Made by loopy, FluBBa, Dwedit, tepples, "
                           "kuwanger, chishm, Mamiya, minitroopa, "
                           "huiminghao, CotoDev & ApacheThunder")
        await ctx.send(embed=em)

    @mod_ds.command(name="gba")
    async def mod_ds_gba(self, ctx: LightningContext) -> None:
        """Gives information on GBARunner2"""
        description = "An open-source Gameboy Advance hypervisor."
        links = ["[Github Repository](https://github.com/RocketRobz/NesDS)",
                 "[GBAtemp thread](https://gbatemp.net/threads/gbarunner2.451970/)",
                 "[GBAtemp compatibility list](https://wiki.gbatemp.net/wiki/GBARunner2)"]
        em = mod_embed("GBARunner2", description, links, discord.Color.blue())
        em.set_footer(text="Made by Gericom")
        await ctx.send(embed=em)

    @mod_ds.command(name="pkmn-chest")
    async def mod_ds_pkmn_chest(self, ctx: LightningContext) -> None:
        """Gives information on pkmn-chest"""
        description = "A Pokémon Bank style app that lets you store and "\
                      "edit Pokémon from the 3rd through 5th generation "\
                      "games on your DS(i)."
        links = ["[Github Repository](https://github.com/Universal-Team/pkmn-chest)",
                 "[Discord Server](https://discord.gg/KDJCfGF)",
                 "[GBAtemp Thread](https://gbatemp.net/threads/release-"
                 "pkmn-chest-a-pokemon-bank-for-the-nintendo-ds-i.549249/)",
                 "[Website](https://universal-team.net/projects/pkmn-chest)"]
        em = mod_embed("pkmn-chest", description, links, 0xBF0300)
        em.set_thumbnail(url="https://elixi.re/i/1ve4.png")
        em.set_footer(text="Made by Universal Team (Mainly by Pk11)")
        await ctx.send(embed=em)

    @mod_ds.command(name='relaunch', aliases=['buttonboot'])
    async def mod_ds_relaunch(self, ctx: LightningContext) -> None:
        """Gives information on Relaunch"""
        description = "A Nintendo DS(i) homebrew that allows the ability"\
                      " to launch an `.nds` file depending on which button"\
                      " you have pressed, similar to NoCash's Unlaunch."
        links = ["[Github Repository](https://github.com/Universal-Team/Relaunch)",
                 "[Discord Server](https://discord.gg/KDJCfGF)"]
        em = mod_embed("Relaunch", description, links, discord.Color.green())
        em.set_thumbnail(url="https://elixi.re/i/e2kb.png")
        em.set_footer(text="Made by Universal Team (Mainly by Flame)")
        await ctx.send(embed=em)

    @mod_ds.command(name='rocketvideoplayer', aliases=['rvp'])
    async def mod_ds_rocketvideoplayer(self, ctx: LightningContext) -> None:
        """Gives information on Rocket Video Player"""
        description = "An open-source video player powered by Rocket "\
                      "Video Technology. It can be used on a Nintendo DSi"\
                      ", a Nintendo 3DS or a Nintendo DS Flashcart by "\
                      "playing a .rvid video file from your SD card."
        links = ["[GBAtemp Thread](https://gbatemp.net/threads/release"
                 "-rocket-video-player-play-videos-with-the-ultimate-in-picture-quality.539163/)",
                 "[Github Repository](https://github.com/RocketRobz/RocketVideoPlayer/releases)",
                 "[Discord Server](https://discord.gg/yqSut8c)"]
        em = mod_embed("Rocket Video Player", description, links, 0xA701E9)
        em.set_thumbnail(url="https://elixi.re/i/jm7f.png")
        em.set_footer(text="Made by RocketRobz",
                      icon_url="https://elixi.re/i/7lh1.png")
        await ctx.send(embed=em)

    @mod_ds.command(name='twilightmenu++', aliases=['twlmenu', 'twilight'])
    async def mod_ds_twlmenu(self, ctx: LightningContext) -> None:
        """Gives information on TWiLightMenu++"""
        description = "An open-source DSi Menu upgrade/replacement allowing "\
                      "you to navigate your SD card and launch a variety of"\
                      " different applications."
        links = ["[GBATemp Thread](https://gbatemp.net/threads/"
                 "ds-i-3ds-twilight-menu-gui-for-ds-i-games-and"
                 "-ds-i-menu-replacement.472200/)",
                 "[Github Repository](https://github.com/DS-Homebrew/TWiLightMenu/releases)",
                 "[Discord Server](https://discord.gg/yqSut8c)"]
        formats = ["Nintendo DS titles",
                   "Sega Game Gear/Master System titles",
                   "NES/Famicom titles",
                   "Super NES/Famicom titles",
                   "Sega Genesis titles",
                   "(Super) Gameboy (Color/Advance) Titles",
                   "Atari 2600 Titles",
                   "DSTWO plugins (requires you to have a DSTWO)",
                   "RocketVideoPlayer & MPEG4 videos"]
        styles = ["Nintendo DSi",
                  "Nintendo 3DS",
                  "R4",
                  "Acekard/akMenu",
                  "SEGA Saturn",
                  "Homebrew Launcher"]
        em = mod_embed("TWiLight Menu++", description, links, 0xA701E9)
        em.add_field(name="Supported Formats", value=', '.join(formats), inline=False)
        stylesformat = '\n\U00002022 '.join(styles)
        em.add_field(name="Styles", value=f"\U00002022 {stylesformat}")
        em.set_footer(text="Made by RocketRobz", icon_url="https://elixi.re/i/7lh1.png")
        await ctx.send(embed=em)

    # Only one command, useless to make it a group
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


def setup(bot: LightningBot) -> None:
    bot.add_cog(Homebrew(bot))
