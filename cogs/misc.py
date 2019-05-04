import discord
from discord.ext import commands
from collections import Counter
import db.mod_check
import asyncio
import colorsys
import random


class Misc(commands.Cog, name='Misc Info'):
    """Misc. Information"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    @commands.command()
    @commands.guild_only()
    async def topic(self, ctx, *, channel: discord.TextChannel = None):
        """Quote the channel topic."""
        if channel is None:
            channel = ctx.message.channel
        embed = discord.Embed(title=f"Channel Topic for {channel}", description=f"{channel.topic}", color=discord.Color.dark_blue())
        await ctx.send(embed=embed)

    @commands.command(aliases=['hastebin'])
    @commands.cooldown(rate=1, per=60.0, type=commands.BucketType.channel)
    async def pastebin(self, ctx, *, message: str):
        """Make a pastebin with your own message"""
        url = await self.bot.haste(message)
        await ctx.send(f"Here's your pastebin. {ctx.author.mention}\n{url}")

    @commands.command(aliases=['ui'])
    @commands.guild_only()
    async def userinfo(self, ctx, *, member: discord.Member=None):
        """Shows userinfo"""

        if member is None:
            member = ctx.author

        embed1 = discord.Embed(title=f'User Info. for {member}', color=member.colour)
        embed1.set_thumbnail(url=f'{member.avatar_url}')
        embed1.add_field(name="Bot?", value=f"{member.bot}")
        embed1.add_field(name="Account Created On:", value=f"{member.created_at}", inline=True)
        embed1.add_field(name='Status:', value=f"{member.status}")
        embed1.add_field(name="Activity:", value=f"{member.activity.name if member.activity else None}", inline=True)
        embed1.add_field(name="Joined:", value=f"{member.joined_at}")
        embed1.add_field(name="Highest Role:", value=f"{member.top_role}", inline=True)
        embed1.set_footer(text=f'User ID: {member.id}')
        await ctx.send(embed=embed1)

    @commands.command()
    async def userinfoid(self, ctx, user_id):
        """Get userinfo by ID"""
        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            await ctx.send(f"❌ I couldn't find {user_id}.")
            return
        embed = discord.Embed(title=f"User Info for {user}", color=user.colour)
        embed.set_thumbnail(url=f"{user.avatar_url}")
        embed.add_field(name="Bot?", value=f"{user.bot}")
        embed.add_field(name="Account Creation Date:", value=f"{user.created_at}")
        embed.set_footer(text=f"User ID: {user.id}")
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command(aliases=['serverinfo'])
    async def server(self, ctx):
        """Shows information about the server"""
        guild = ctx.guild # Simplify 
        embed = discord.Embed(title=f"Server Info for {guild.name}")
        embed.add_field(name='Owner', value=guild.owner)
        embed.add_field(name="ID", value=guild.id)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(name="Creation", value=guild.created_at)
        member_by_status = Counter(str(m.status) for m in guild.members) # Little snippet taken from R. Danny. Under the MIT License
        sta = f'<:online:572962188114001921> {member_by_status["online"]} ' \
              f'<:idle:572962188201820200> {member_by_status["idle"]} ' \
              f'<:dnd:572962188134842389> {member_by_status["dnd"]} ' \
              f'<:offline:572962188008882178> {member_by_status["offline"]}\n\n' \
              f'Total: {guild.member_count}'    

        embed.add_field(name="Members", value=sta)
        embed.add_field(name="Emoji Count", value=f"{len(guild.emojis)}")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def membercount(self, ctx):
        """Prints the server's member count"""
        embed = discord.Embed(title=f"Member Count", description=f"{ctx.guild.name} has {ctx.guild.member_count} members.", color=discord.Color.orange())
        await ctx.send(embed=embed)


    @commands.group()
    async def announce(self, ctx):
        """Announcements"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @announce.command()
    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def interactive(self, ctx, channel: discord.TextChannel):
        """Interactive Announcement Embed Generator. Moderators only."""
        def check(ms):
            # Look for the message sent in the same channel where the command was used
            # As well as by the user who used the command.
            return ms.channel == ctx.message.channel and ms.author == ctx.message.author

        await ctx.send(content='What would you like the title of your announcement to be?')

        try:
            msg = await self.bot.wait_for('message', timeout=65.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long. Bye.')
        title = msg.content # Set the title

        await ctx.send(content='What would you like to set as the description?')
        try:
            msg = await self.bot.wait_for('message', timeout=300.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long. Bye')
        desc = msg.content

        msg = await ctx.send(content=f'Now sending the embed to {channel.mention}...')
        embed = discord.Embed(title=title, description=desc)
        embed.set_author(name=ctx.message.author, icon_url=ctx.message.author.avatar_url)
        embed.timestamp = msg.created_at
        await channel.send(embed=embed, content=None)
        return

    @announce.command()
    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def simple(self, ctx, channel: discord.TextChannel, *, text):
        """Make a simple announcement""" # Basically the speak command, but mentions the author.
        await channel.send(f"Announcement from {ctx.author.mention}:\n\n{text}")

    @announce.command(aliases=['rcembed', 'colorembed'])
    @commands.guild_only()
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def random(self, ctx, channel: discord.TextChannel):
        """Chooses a random color and uses it for the embed. (Interactive) """
        def check(ms):
            # Look for the message sent in the same channel where the command was used
            # As well as by the user who used the command.
            return ms.channel == ctx.message.channel and ms.author == ctx.message.author

        await ctx.send(content='What would you like the title of your announcement to be?')

        try:
            msg = await self.bot.wait_for('message', timeout=65.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long. Bye.')
        title = msg.content # Set the title

        await ctx.send(content='What would you like to set as the description?')
        try:
            msg = await self.bot.wait_for('message', timeout=300.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long. Bye')
        desc = msg.content

        msg = await ctx.send(content=f'Now sending the embed to {channel.mention}...')
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)] # Chooses a random color
        embed = discord.Embed(title=title, description=desc, colour=discord.Color.from_rgb(*color_random))
        embed.set_author(name=ctx.message.author, icon_url=ctx.message.author.avatar_url)
        embed.timestamp = msg.created_at
        await channel.send(embed=embed, content=None)
        return





def setup(bot):
    bot.add_cog(Misc(bot))
