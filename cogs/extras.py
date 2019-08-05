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

    @commands.command()
    async def poll(self, ctx, *, question: str):
        """Creates a simple poll with thumbs up, thumbs down, and shrug as reactions"""
        embed = discord.Embed(title="Poll", description=f'Question: {question}', 
                              color=discord.Color.dark_blue())
        embed.set_author(name=f'{ctx.author}', icon_url=f'{ctx.author.avatar_url}')
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        await msg.add_reaction("🤷")
    
    @poll.error
    async def poll_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send('Please add a question.')

    @commands.command()
    async def texttobinary(self, ctx, *, text: str):
        """Converts text to binary"""
        async with ctx.typing():
            msg = " ".join(f"{ord(i):08b}" for i in text)
        await ctx.send(f"```{msg}```")

def setup(bot):
    bot.add_cog(Extras(bot))