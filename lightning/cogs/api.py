"""
Lightning.py - A personal Discord bot
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

import math
import re
import urllib.parse
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands
from discord.ext import menus as dmenus

from lightning import (LightningBot, LightningCog, LightningContext, command,
                       flags, group)
from lightning.utils import helpers, paginator


class GelbooruPost:
    def __init__(self, payload):
        self.id = payload['id']
        self.tags = payload['tags'].split(" ")
        self.file_url = payload['file_url']
        self.rating = payload['rating']

    def __str__(self):
        return self.file_url

    def __repr__(self):
        return f"<GelbooruPost id={self.id} rating={self.rating} file_url={self.file_url}>"


class GelbooruMenuPages(dmenus.MenuPages):
    def __init__(self, source, **kwargs):
        super().__init__(source, **kwargs)

    @dmenus.button("\N{LABEL}", position=dmenus.Last(3))
    async def show_tags(self, payload) -> None:
        """Shows all tags for this post"""
        embed = self.message.embeds[0]
        if "See all tags" in embed.description:
            return
        all_tags = "\n".join(self.source.entries[self.current_page].tags)
        link = await helpers.haste(self.ctx.bot.aiosession, f"All Tags:\n{all_tags}")
        embed.description = (f"{embed.description[:-22]} [See all tags]({link})")
        await self.message.edit(embed=embed)


class GelbooruMenu(dmenus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, menu, entries):
        offset = menu.current_page
        tags = entries.tags[0:5]
        description = "**Rating**: {}\n**Tags**: {} (Only showing 5 tags)".format(entries.rating.capitalize(),
                                                                                  ", ".join(tags))
        embed = discord.Embed(title=entries.id, description=description)
        embed.set_image(url=entries.file_url)
        embed.set_footer(text=f"Page {offset + 1}/{len(self.entries)}")
        return embed


class CratesIOResponse:
    __slots__ = ('crates', 'total', 'previous_page', 'next_page')

    def __init__(self, data: dict):
        self.crates = [Crate(x) for x in data['crates']]
        self.total = data['meta']['total']
        self.previous_page = data['meta']['prev_page']
        self.next_page = data['meta']['next_page']


class Crate:
    __slots__ = ('id', 'name', 'description', 'downloads', 'homepage', 'documentation', 'repository',
                 'exact_match', 'newest_version', 'max_version')

    def __init__(self, data: dict):
        self.id = data['id']
        self.name = data['name']
        self.description = data['description'].strip()
        self.downloads = data['downloads']
        self.homepage = data['homepage']
        self.documentation = data['documentation']
        self.repository = data['repository']
        self.exact_match = data['exact_match']

        self.newest_version = data['newest_version']
        self.max_version = data['max_version']

    def __repr__(self):
        return f"<Crate id={self.id}>"


class CrateViewer(dmenus.KeysetPageSource):
    def __init__(self, search_term: str, *, session: aiohttp.ClientSession):
        self.session = session
        self.search_term = search_term

    def is_paginating(self) -> bool:
        return True

    async def request(self, query: str) -> dict:
        async with self.session.get(f"https://crates.io/api/v1/crates{query}") as resp:
            data = await resp.json()
        return data

    async def get_page(self, specifier) -> CratesIOResponse:
        query = f"?q={urllib.parse.quote(self.search_term)}"
        if specifier.reference is not None:
            if specifier.direction is dmenus.PageDirection.after:
                if specifier.reference.next_page is None:
                    raise ValueError
                query = specifier.reference.next_page
            else:
                if specifier.reference.previous_page is None:
                    raise ValueError
                query = specifier.reference.previous_page
        elif specifier.direction is dmenus.PageDirection.before:
            data = await self.request(query)
            query += f"&page={math.ceil(data['meta']['total'] / 10)}"

        data = await self.request(query)

        obj = CratesIOResponse(data)
        if not obj.crates:
            raise ValueError

        return obj

    async def format_page(self, menu, page) -> discord.Embed:
        v = "\n".join(f"**Exact Match** [{p.name}](https://crates.io/crates/{p.id})" if p.exact_match else
                      f"[{p.name}](https://crates.io/crates/{p.id})" for p in page.crates)
        embed = discord.Embed(title=f"Results for {self.search_term}", color=0x3B6837,
                              description=v)
        return embed


class API(LightningCog):
    """Commands that interact with different APIs"""

    def clean_text(self, text: str) -> str:
        html = re.compile('<.*?>')
        return re.sub(html, '', text)

    @group(invoke_without_command=True)
    async def blacklightning(self, ctx: LightningContext, season: int) -> None:
        """Gives summaries for episodes of Black Lightning."""
        if season > 4 or season <= 0:
            await ctx.send("That season doesn\'t exist")
            return

        resp = await ctx.prompt("This can potentially give spoilers to the show. Are you sure you want to proceed?",
                                delete_after=True)
        if not resp:
            return

        data = await ctx.request("http://api.tvmaze.com/shows/20683/episodes")
        episode_info = []
        for e in data:
            if e['season'] == season:
                ts = datetime.fromisoformat(e['airstamp']).strftime('%Y-%m-%d %H:%M UTC')
                summary = e['summary']
                if summary:
                    summary = self.clean_text(summary)
                else:
                    summary = "No information available!"
                episode_info.append((e['name'], f"Episode Info: {summary}\n**Air Date:** {ts}"))

        p = paginator.InfoMenuPages(paginator.FieldMenus(entries=episode_info, per_page=4),
                                    delete_message_after=True, check_embeds=True, timeout=60.0)
        try:
            await p.start(ctx, channel=await ctx.author.create_dm())
        except discord.Forbidden:
            await p.start(ctx)

    @blacklightning.command(name="episode")
    async def episode_info(self, ctx: LightningContext, season: int, episode: int) -> None:
        """Gives info on a certain episode of Black Lightning"""
        url = f"http://api.tvmaze.com/shows/20683/episodebynumber?season={season}&number={episode}"
        resp = await ctx.prompt("This can potentially give spoilers to the show. Are you sure you want to proceed?",
                                delete_after=True)
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

    @flags.add_flag("--limit", "-l", converter=int, help="How many results to search for")
    @commands.is_nsfw()
    @command(cls=flags.FlagCommand)
    async def gelbooru(self, ctx: LightningContext, **flags) -> None:
        """Searches images on gelbooru"""
        tags = urllib.parse.quote(flags['rest'], safe="")
        limit = 20 if not flags['limit'] else flags['limit']
        url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={limit}&tags={tags}"
        data = await ctx.request(url)
        posts = []
        for x in data:
            x = GelbooruPost(x)
            bad_tags = any(tag in ['loli', 'cub', 'shota', 'child'] for tag in x.tags)
            if bad_tags:
                continue
            else:
                posts.append(x)

        if not posts:
            raise commands.BadArgument("Either you provided bad tags, the tags you searched are blacklisted, or no "
                                       "results were found. \N{SHRUG}")

        pages = GelbooruMenuPages(GelbooruMenu(posts), delete_message_after=True, check_embeds=True)
        await pages.start(ctx)

    @command()
    @commands.is_nsfw()
    @commands.bot_has_permissions(embed_links=True)
    async def neko(self, ctx: LightningContext) -> None:
        resp = await ctx.request("https://nekos.life/api/v2/img/neko")
        embed = discord.Embed(color=discord.Color.magenta())
        embed.set_image(url=resp['url'])
        await ctx.send(embed=embed)

    @command()
    async def rtfs(self, ctx: LightningContext, *, entity: str) -> None:
        """Shows source for an entity in discord.py"""
        data = await ctx.request(f"https://rtfs.eviee.me/dpy?search={urllib.parse.quote(entity)}")

        if not data:
            await ctx.send("Couldn't find anything...")
            return

        embed = discord.Embed(title=f"RTFS: {entity}", description="", color=discord.Color.blurple())
        data = data[:12]
        embed.description = '\n'.join(data)
        embed.set_footer(text="Thanks Myst for the API")
        await ctx.send(embed=embed)

    @command()
    async def qr(self, ctx: LightningContext, *, text: str) -> None:
        """Generates a QR code"""
        await ctx.send(f"https://api.qrserver.com/v1/create-qr-code/?data={text.replace(' ', '+')}")

    @group(invoke_without_command=True)
    async def crate(self, ctx: LightningContext) -> None:
        """Crate related commands"""
        await ctx.send_help('crate')

    @crate.command(name='browse', aliases=['search'])
    async def browsecrates(self, ctx: LightningContext, *, crate: str) -> None:
        """Searches for a crate"""
        menu = dmenus.MenuKeysetPages(CrateViewer(crate, session=self.bot.aiosession), clear_reactions_after=True,
                                      check_embeds=True)
        await menu.start(ctx)

    @crate.command(name='get', enabled=False)
    async def showcrate(self, ctx: LightningContext, *, crate: str) -> None:
        resp = await ctx.request(f"https://crates.io/api/v1/crates/{crate}")
        obj = Crate(resp)
        embed = discord.Embed(title=obj.name, description=obj.description)
        embed.set_footer(text="Exact match" if obj.exact_match else "Closest match")
        await ctx.send(embed=embed)


def setup(bot: LightningBot):
    bot.add_cog(API(bot))
