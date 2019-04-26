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
        print(f'Cog "{self.qualified_name}" loaded')

    @commands.command()
    async def peng(self, ctx):
        """Uhhh ping?"""
        await ctx.send(f"My ping is uhhh `{random.randint(31,150)}ms`")

    @commands.command(name='top-role', aliases=['toprole'])
    @commands.guild_only()
    async def show_toprole(self, ctx, *, member: discord.Member=None):
        """Shows the member's highest role."""
        if member is None:
            member = ctx.author
        await ctx.send(f'🎉 The top role for {member.display_name} is **{member.top_role.name}**')

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
    @commands.command(name='embed')
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

    @commands.command(hidden=True)
    async def emojiid(self, ctx):
        """Shows emotes by ID"""

        output = ""
        for emote in self.bot.emojis:
            if not emote.animated:
                continue
            output += f'`:{emote.name}: ID {emote.id}\n'
        await ctx.send("__List of animated emojis with IDs:__\n\n" + output)

# Taken from Kurisu's Extras Cog. Readapted to add different emotes to it. Kurisu is under the Apache 2.0 License.
# https://github.com/nh-server/Kurisu/blob/port/LICENSE.txt
    @commands.group()
    async def seasonal(self, ctx):
        """Seasonal Emojis"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.guild_only()
    @seasonal.command()
    async def meow(self, ctx):
        """Adds a Meow in front of your name"""
        meow = 'Meow'
        month = datetime.date.today().month
        day = datetime.date.today().day
        if month == 3 and day == 31 or month == 4 and day == 1:
            member = ctx.author
            if member.nick and member.nick[-1] == meow:
                await ctx.send("Your nickname already starts with Meow!")
            elif member.name[-1] == meow and not member.nick:
                await ctx.send("Your name already starts with Meow!")
            else:
                try:
                    await ctx.author.edit(nick=f"{meow}{member.display_name}")
                except discord.errors.Forbidden:
                    await ctx.send("<:noblobaww:561618920096792596>  I can't change your nickname!")
                    return
                await ctx.send(f"Your nickname is now `{member.display_name}`!")
        else:
            await ctx.send("This day is not old/new enough!")

    @commands.guild_only()
    @seasonal.command()
    async def cat(self, ctx):
        """Adds a cat at the end of your name"""
        meow = '🐱'
        month = datetime.date.today().month
        day = datetime.date.today().day
        if month == 3 and day == 31 or month == 4 and day == 1:
            member = ctx.author
            if member.nick and member.nick[-1] == meow:
                await ctx.send("Your nickname already ends with a cat!")
            elif member.name[-1] == meow and not member.nick:
                await ctx.send("Your name already ends with a cat!")
            else:
                try:
                    await ctx.author.edit(nick=f"{member.display_name} {meow}")
                except discord.errors.Forbidden:
                    await ctx.send("<:noblobaww:561618920096792596>  I can't change your nickname!")
                    return
                await ctx.send(f"Your nickname is now `{member.display_name}`!")
        else:
            await ctx.send("This day is not old/new enough!")

    @commands.guild_only()
    @seasonal.command()
    async def sun(self, ctx):
        """Adds a sun emoji at the end of your name"""
        sun = '🌞'
        month = datetime.date.today().month
        if month == 6 or month == 7 or month == 8:
            member = ctx.author
            if member.nick and member.nick[-1] == sun:
                await ctx.send("Your nickname already ends with a sun!")
            elif member.name[-1] == sun and not member.nick:
                await ctx.send("Your name already ends with a sun!")
            else:
                try:
                    await ctx.author.edit(nick=f"{member.display_name} {sun}")
                except discord.errors.Forbidden:
                    await ctx.send("<:noblobaww:561618920096792596> I can't change your nickname!")
                    return
                await ctx.send(f"Your nickname is now `{member.display_name}`!")
        else:
            await ctx.send("This month is not old/new enough! <:noawwshades:563435435427102740>")

def setup(bot):
    bot.add_cog(Extras(bot))