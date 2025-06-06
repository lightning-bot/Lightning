"""
Lightning.py - A Discord bot
Copyright (C) 2019-2025 LightSage

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

import re
import urllib.parse
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Optional, Tuple

import discord
from bs4 import BeautifulSoup
from discord import app_commands
from rapidfuzz import fuzz, process

from lightning import LightningCog, command, group, hybrid_command
from lightning.utils import helpers, paginator

if TYPE_CHECKING:
    from lightning import LightningBot, LightningContext


SPACE_ID = "JJ4jkpoAhx9Lyu6LuBJs"
ORG_ID = ""


class API(LightningCog):
    """Commands that interact with different APIs"""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self.pg_rtfm_cache = {}

    def cog_unload(self):
        self.pg_rtfm_cache.clear()

    def clean_text(self, text: str) -> str:
        html = re.compile('<.*?>')
        return html.sub('', text)

    @group(invoke_without_command=True)
    async def blacklightning(self, ctx: LightningContext, season: int) -> None:
        """Gives summaries for episodes of Black Lightning."""
        if season > 4 or season <= 0:
            await ctx.send("That season doesn\'t exist")
            return

        resp = await ctx.confirm("This can potentially give spoilers to the show. Are you sure you want to proceed?")
        if not resp:
            return

        data = await ctx.request("http://api.tvmaze.com/shows/20683/episodes")
        episode_info = []
        for e in data:
            if e['season'] == season:
                ts = discord.utils.format_dt(datetime.fromisoformat(e['airstamp']))
                summary = e['summary']
                if summary:
                    summary = self.clean_text(summary)
                else:
                    summary = "No information available!"
                episode_info.append((e['name'], f"Episode Info: {summary}\n**Air Date:** {ts}"))

        p = paginator.Paginator(paginator.FieldMenus(entries=episode_info, per_page=4),
                                context=ctx, timeout=60.0)
        await p.start(wait=False)

    @blacklightning.command(name="episode")
    async def episode_info(self, ctx: LightningContext, season: int, episode: int) -> None:
        """Gives info on a certain episode of Black Lightning"""
        url = f"http://api.tvmaze.com/shows/20683/episodebynumber?season={season}&number={episode}"
        resp = await ctx.confirm("This can potentially give spoilers to the show. Are you sure you want to proceed?")
        if not resp:
            return

        data = await ctx.request(url)
        em = discord.Embed(title=data['name'], url=data['url'])
        em.timestamp = datetime.fromisoformat(data['airstamp'])
        em.set_footer(text="Aired on")

        if data['summary']:
            em.add_field(name="Summary", value=self.clean_text(data['summary']))
        if data['image']:
            em.set_image(url=data['image']['original'])

        await ctx.send(embed=em, delete_after=60.0)

    @hybrid_command()
    @app_commands.describe(text="The text or URL for the QR code")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def qr(self, ctx: LightningContext, *, text: str) -> None:
        """Generates a QR code"""
        await ctx.send(f"https://api.qrserver.com/v1/create-qr-code/?qzone=4&data={urllib.parse.quote(text)}")

    def get_match(self, word_list: list, word: str, score_cutoff: int = 60) -> Optional[Tuple[str, float, int]]:
        result = process.extractOne(word, word_list, scorer=fuzz.WRatio,
                                    score_cutoff=score_cutoff, processor=lambda a: a.lower())
        if not result:
            return None
        return result

    def _build_pg_cache(self, content):
        soup = BeautifulSoup(content, "lxml")
        contents = {}
        divs = soup.find("div", id="BOOKINDEX").find_all("dt")
        for x in divs:
            links = [f"https://www.postgresql.org/docs/15/{x['href']}" for x in x.find_all("a", class_="indexterm")]
            for name in x.text.split(","):
                contents[name.strip()] = links
        self.pg_rtfm_cache: Dict[str, str] = contents
        return self.pg_rtfm_cache

    async def search_pg_docs(self, entry: str) -> Optional[Tuple[str, str]]:
        if not self.pg_rtfm_cache:
            raw = await helpers.request("https://www.postgresql.org/docs/15/bookindex.html", self.bot.aiosession,
                                        return_text=True)
            entries = self._build_pg_cache(raw)
        else:
            entries = self.pg_rtfm_cache

        match = self.get_match(list(entries.keys()), entry, 40)

        if not match:
            return None

        return (match[0], entries[match[0]])

    @command()
    async def rtfm(self, ctx: LightningContext, *, entity: Optional[str] = None):
        """Searches PostgreSQL docs for an entity"""
        if not entity:
            await ctx.send("https://www.postgresql.org/docs/15/bookindex.html")
            return

        r = await self.search_pg_docs(entity)

        if not r:
            await ctx.send("https://www.postgresql.org/docs/15/bookindex.html")
            return

        links = '\n'.join(r[1])

        await ctx.send(f"> {r[0]}\n{links}")

    # @hybrid_command()
    async def faq(self, ctx: LightningContext, *, question: str):
        """Searches for something in the bot's documentation"""
        await ctx.defer()

        payload = {"query": question}
        async with self.bot.aiosession.post(f"https://api.gitbook.com/v1/orgs/{ORG_ID}/sites/{SPACE_ID}/search/ask",
                                            json=payload, headers={"Content-Type": "application/json"}) as r:
            data = await r.json()

        if not data:
            async with self.bot.aiosession.get(f"https://api.gitbook.com/v1/spaces/{SPACE_ID}/search/questions",
                                               headers={"Content-Type": "application/json"}) as r:
                query = await r.json()
            rec = '\n'.join(query['questions'][:3])
            await ctx.send(f"**Please ask a more specific question. Some examples include**:\n{rec}")
            return

        embed = discord.Embed()
        embed.set_footer(text="💡 This answer is powered by AI, so it may or may not be wrong.")
        await ctx.send(data['answer']['text'], embed=embed, ephemeral=True)
