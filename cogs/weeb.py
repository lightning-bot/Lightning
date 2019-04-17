import aiohttp
import discord
import colorsys
import random
from discord.ext import commands


class Weeb(commands.Cog):
    """Weeb Features"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        print(f'Cog "{self.qualified_name}" loaded')

    @commands.command(name='headpat')
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
            person = await (commands.MemberConverter()).convert(ctx=ctx, argument=person) # Reimplementation of NekoBot/Kawaii Bot slap function. May change it in the near future.
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

    
    @commands.command()
    async def tuturu(self, ctx):
        """tuturu!"""
        await ctx.send('https://cdn.discordapp.com/emojis/562686801043521575.png?v=1')


def setup(bot):
    bot.add_cog(Weeb(bot))