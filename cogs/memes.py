import discord
from discord.ext import commands
import random


class Memes(commands.Cog):
    def __init__(self, bot):
        """Approved™ memes"""
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.command()
    async def listmemes(self, ctx):
        """Lists meme commands"""
        # Taken from Kurisu until I make a better one. 
        # Kurisu is under the Apache 2.0 License. https://github.com/nh-server/Kurisu/blob/port/LICENSE.txt
        msg = "```css\n"
        msg += ", ".join([x.name for x in self.get_commands() if x != self.listmemes])
        msg += "```"
        await ctx.send(msg)

    @commands.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def astar(self, ctx):
        """Here's a star just for you."""
        await ctx.send(f"{ctx.author.display_name}: https://i.imgur.com/vUrBPZr.png")

    @commands.command(hidden=True, aliases=['inori'])
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def hifumi1(self, ctx):
        """Disappointment"""
        await ctx.send(f"{ctx.author.display_name}: https://i.imgur.com/jTTHQLs.gifv")

    @commands.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def thisisgit(self, ctx):
        """Git in a nutshell"""
        await ctx.send(f"{ctx.author.display_name}: https://gitlab.com/LightSage/bunches-of-images/raw/master/lightning/xkcd.png") # Using the img hosted on Gitlab for now   

    @commands.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def knuckles(self, ctx):
        # It's just as bad
        re_list = ['to frii gaems', 'to bricc', 'to get frii gaems', 'to build sxos',
                   'to play backup games', 'to get unban', 'to get reinx games',
                   'to build atmos', 'to brick my 3ds bc ebay scammed me', 'to plz help me'] 
        whenlifegetsatyou = ['?!?!?', '?!?!', '.', '!!!!', '!!', '!']
        await ctx.send(f"Do you know da wae {random.choice(re_list)}{random.choice(whenlifegetsatyou)}")
       


def setup(bot):
    bot.add_cog(Memes(bot))
