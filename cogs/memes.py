import discord
from discord.ext import commands


class Memes(commands.Cog):

    def __init__(self, bot):
        """Approved™ memes"""
        self.bot = bot
        print(f'Cog "{self.qualified_name}" loaded')

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

    @commands.command(hidden=True)
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.channel)
    async def hifumi1(self, ctx):
        """Disappointment"""
        await ctx.send(f"{ctx.author.display_name}: https://i.imgur.com/jTTHQLs.gifv")
       
    


def setup(bot):
    bot.add_cog(Memes(bot))