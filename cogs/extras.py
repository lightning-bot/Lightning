import discord
import random
import time
import datetime
from database import Roles, Base
from discord.ext import commands
import aiohttp
import db.mod_check


class Extras(commands.Cog):
    """Extra stuff"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.command()
    async def peng(self, ctx):
        """Uhhh ping?"""
        await ctx.send(f"My ping is uhhh `{random.randint(31,150)}ms`")


    @commands.command()
    @commands.guild_only()
    async def avatar(self, ctx, *, member: discord.Member = None):
        """Get someone's avatar."""
        if member is None:
            member = ctx.author
        embed = discord.Embed(color=discord.Color.blue(), description=f"[Link to Avatar]({member.avatar_url})")
        embed.set_author(name=f"{member.name}\'s Avatar")
        embed.set_image(url=member.avatar_url)
        await ctx.send(embed=embed)
        
    @commands.command(aliases=['say'])
    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def speak(self, ctx, channel: discord.TextChannel, *, inp):
        """Say something through the bot to the specified channel. Staff only."""
        await channel.trigger_typing()
        await channel.send(inp)
    
    @commands.guild_only()
    @commands.command()
    async def listemotes(self, ctx):
        """Prints a fancy list of the server's emotes"""
        if len(ctx.guild.emojis) == 0:
            return await ctx.send("This server has no emotes!")
            
        paginator = commands.Paginator(suffix='', prefix='')
        for emoji in ctx.guild.emojis:
            paginator.add_line(f'{emoji} -- `{emoji}`')

        for page in paginator.pages:
            await ctx.send(page)


def setup(bot):
    bot.add_cog(Extras(bot))