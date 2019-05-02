# Making this cog to help people change over to the new commands.
import discord
from discord.ext import commands

class Old_Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')


    @commands.command(aliases=['lightning'], hidden=True)
    async def credits(self, ctx):
        embed = discord.Embed(title="Note", description="This command has been changed to `l.about`", color=discord.Color.dark_green())
        await ctx.send(embed=embed)

    @commands.command(aliases=['set', 'settings'], hidden=True)
    async def edit(self, ctx):
        embed = discord.Embed(title="Note", description="This command no longer exists. To setup the bot, use `l.help Configuration`", color=discord.Color.dark_green())
        await ctx.send(embed=embed)

    @commands.command(aliases=[], hidden=True)
    async def bam(self, ctx):
        embed = discord.Embed(title="Note", description="This command no longer exists. It will be added soon:tm:", color=discord.Color.dark_green())
        await ctx.send(embed=embed)

    @commands.command(aliases=[], hidden=True)
    async def bothelper(self, ctx):
        embed = discord.Embed(title="Note", description="This command no longer exists. It will be added soon:tm:", color=discord.Color.dark_green())
        await ctx.send(embed=embed)

    @commands.command(aliases=[], hidden=True)
    async def roll(self, ctx):
        embed = discord.Embed(title="Note", description="This command no longer exists.", color=discord.Color.dark_green())
        await ctx.send(embed=embed)

    @commands.command(aliases=[], hidden=True)
    async def mylevel(self, ctx):
        embed = discord.Embed(title="Note", description="This command no longer exists.", color=discord.Color.dark_green())
        await ctx.send(embed=embed)



def setup(bot):
    bot.add_cog(Old_Commands(bot))