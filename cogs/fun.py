import aiohttp
import discord
from discord.ext import commands


class Fun(commands.Cog):
    """Fun Stuff"""
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        print(f'Cog "{self.qualified_name}" loaded')

    @commands.command()
    async def cat(self, ctx):
        async with self.session.get('http://aws.random.cat/meow') as resp:
            data = await resp.json()
        embed = discord.Embed(title="Meow <:meowawauu:559383939513581569>", color=discord.Color.teal())
        embed.set_image(url=data['file'])
        embed.set_footer(text="Powered by random.cat", icon_url="https://purr.objects-us-east-1.dream.io/static/ico/favicon-96x96.png")
        await ctx.send(embed=embed)



def setup(bot):
    bot.add_cog(Fun(bot))