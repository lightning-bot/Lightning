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

from discord.ext import commands
import discord
from bolt.paginator import FieldPages
from datetime import datetime
import re
from bs4 import BeautifulSoup


# Once again TODO: Add plonks
class Misc(commands.Cog):
    """Commands that don't belong in a specific category"""
    def __init__(self, bot):
        self.bot = bot
        # self.requests_count = 0
        self.ratelimited = False

    def clean_text(self, text):
        html = re.compile('<.*?>')
        return re.sub(html, '', text)

    def spoilerize(self, text):
        return f"|| {text} ||"

    @commands.group(invoke_without_command=True)
    @commands.is_nsfw()
    async def blacklightning(self, ctx, season: int = 3):
        """Gives summaries for episodes of Black Lightning.

        This can contain spoilers, which is why this command
        can only be used in nsfw channels or DMs."""
        if season > 3 or season <= 0:
            return await ctx.send(f"That season doesn\'t exist")
        base_url = "http://api.tvmaze.com/shows/20683/episodes"
        episode_info = []
        async with self.bot.aiosession.get(base_url) as resp:
            if resp.status == 200:
                text = await resp.json()
            elif resp.status == 429:
                self.ratelimited = True
                return await ctx.send(f"Temporarily ratelimited. "
                                      f"Try again in a few seconds. (Status: {resp.status})")
        for e in text:
            if e['season'] == season:
                ts = datetime.fromisoformat(e['airstamp']).strftime('%Y-%m-%d %H:%M UTC')
                summary = e['summary']
                if summary:
                    summary = self.clean_text(summary)
                else:
                    summary = "No information available!"
                episode_info.append((e['name'], f"Episode Info: {summary}\n**Air Date:** {ts}"))
        p = FieldPages(ctx, entries=episode_info, per_page=5)
        await p.paginate()

    @blacklightning.command(name="episode")
    @commands.is_nsfw()
    async def episode_info(self, ctx, season: int, episode: int):
        """Gives info on a certain episode of Black Lightning"""
        url = f"http://api.tvmaze.com/shows/20683/episodebynumber?season={season}&number={episode}"
        async with self.bot.aiosession.get(url) as resp:
            if resp.status == 200:
                text = await resp.json()
            elif resp.status == 429:
                self.ratelimited = True
                return await ctx.send(f"Temporarily ratelimited. "
                                      f"Try again in a few seconds. (Status: {resp.status})")
            elif resp.status == 404:
                return await ctx.send("Could not get details for that!")
        em = discord.Embed(title=text['name'])
        em.timestamp = datetime.fromisoformat(text['airstamp'])
        if text['summary']:
            em.add_field(name="Summary", value=self.clean_text(text['summary']))
        # if text['image']:
        #    em.set_image(url=text['image']['original'])
        em.url = text['url']
        await ctx.send(embed=em)

    @commands.command(name="garfield")
    async def random_garfieldcomic(self, ctx):
        """Displays a random garfield comic

        Powered by GoComics"""
        url = "https://www.gocomics.com/random/garfield"
        async with self.bot.aiosession.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

        img_url = soup.find(attrs={'class': 'item-comic-image'}).img['src']

        embed = discord.Embed(title="Random Garfield Comic", colour=discord.Colour(0xFF9900))
        embed.set_image(url=img_url)
        embed.set_footer(text=f'Requested by {ctx.author}', icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Misc(bot))
