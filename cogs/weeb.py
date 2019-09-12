# Lightning.py - The Successor to Lightning.js
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
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version

import aiohttp
import discord
import colorsys
import random
from discord.ext import commands


class Weeb(commands.Cog):
    """Weeb Features"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    @commands.command(name='headpat')
    @commands.bot_has_permissions(embed_links=True)
    async def headpat(self, ctx):
        """Random headpat gifs"""
        async with self.session.get("https://nekos.life/api/pat") as resp:
            headpat = await resp.json()
        url = headpat["url"]
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)]
        embed = discord.Embed(title='Headpat, owo', colour=discord.Color.from_rgb(*color_random))
        embed.set_image(url=url)
        embed.set_footer(text="Powered by nekos.life", icon_url="https://nekos.life/static/icons/favicon-194x194.png")
        await ctx.send(embed=embed)

    @commands.command(name='slap')
    @commands.bot_has_permissions(embed_links=True)
    async def slap(self, ctx, person):
        """Slap yourself or someone."""
        async with self.session.get("https://nekos.life/api/v2/img/slap") as resp:
            slap = await resp.json()
        url = slap["url"]
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)]
        embed = discord.Embed(colour=discord.Color.from_rgb(*color_random))
        embed.set_image(url=url)
        embed.set_footer(text="Powered by nekos.life", icon_url="https://nekos.life/static/icons/favicon-194x194.png")
        try:
            person = await (commands.MemberConverter()).convert(ctx=ctx, argument=person)
        except commands.BadArgument:
            pass
        if isinstance(person, discord.Member) and person.id == ctx.author.id:
            embed.title = (f"*{ctx.author.name} slapped themself.*")
        else:
            if isinstance(person, discord.Member):
                name = person.name
            else:
                name = person[:30]
            embed.title = (f"*{ctx.author.name} slapped {name}*")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Weeb(bot))
