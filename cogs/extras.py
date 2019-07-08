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
    @commands.command(name='make-embed')
    @commands.bot_has_permissions(embed_links=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def embed_command(self, ctx):
        """Interactive Embed Generator. Moderators only."""
        def check(ms):
            # Look for the message sent in the same channel where the command was used
            # As well as by the user who used the command.
            return ms.channel == ctx.message.channel and ms.author == ctx.message.author

        await ctx.send(content='What would you like the title to be?')

        msg = await self.bot.wait_for('message', check=check)
        title = msg.content # Set the title

        await ctx.send(content='What would you like the Description to be?')
        msg = await self.bot.wait_for('message', check=check)
        desc = msg.content

        msg = await ctx.send(content='Now generating the embed...')
        embed = discord.Embed(
            title=title,
            description=desc,
            color=0x1ABC9C,
        )
        embed.set_thumbnail(url=self.bot.user.avatar_url)
        embed.set_author(
            name=ctx.message.author.name,
            icon_url=ctx.message.author.avatar_url
        )
        await msg.edit(
            embed=embed,
            content=None
        )
        return


def setup(bot):
    bot.add_cog(Extras(bot))