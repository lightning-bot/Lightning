import discord
from discord.ext import commands
from collections import Counter
import db.mod_check
import asyncio
import colorsys
import random
import io
from PIL import Image


class Misc(commands.Cog):
    """Misc. Information"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

    def finalize_image(self, image): # Image Save
        image_b = Image.open(io.BytesIO(image))
        image_file = io.BytesIO()
        image_b.save(image_file, format="png")
        image_file.seek(0)
        return image_file

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
    @commands.bot_has_permissions(embed_links=True)
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
    @commands.bot_has_permissions(embed_links=True)
    async def userinfoid(self, ctx, user_id):
        """Get userinfo by ID"""
        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            return await ctx.send(f"❌ I couldn't find `{user_id}`.")
        embed = discord.Embed(title=f"User Info for {user}", color=user.colour)
        embed.set_thumbnail(url=f"{user.avatar_url}")
        embed.add_field(name="Bot?", value=f"{user.bot}")
        embed.add_field(name="Account Creation Date:", value=f"{user.created_at}")
        embed.set_footer(text=f"User ID: {user.id}")
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
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
        embed.add_field(name="Verification Level", value=guild.verification_level)
        boosts = f"Tier: {guild.premium_tier}\n"\
                 f"Users Boosted Count: {guild.premium_subscription_count}"
        embed.add_field(name="Nitro Server Boost", value=boosts)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def membercount(self, ctx):
        """Prints the server's member count"""
        embed = discord.Embed(title=f"Member Count", description=f"{ctx.guild.name} has {ctx.guild.member_count} members.", color=discord.Color.orange())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(change_nickname=True)
    @commands.bot_has_permissions(change_nickname=True)
    async def setnick(self, ctx, *, nick: str):
        """Set your own nickname.
        Clear your nickname by just sending .resetnick"""
        author = ctx.author 
        try:
            await author.edit(nick=nick, reason=str(ctx.author))
        except discord.errors.Forbidden:
            return await ctx.send("💢 I can't change your nickname.")

        
        await ctx.send(f"{ctx.author.mention}: I've set your nickname to `{nick}`.")

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(change_nickname=True)
    @commands.bot_has_permissions(change_nickname=True)
    async def resetnick(self, ctx):
        """Resets/clears your nickname."""
        author = ctx.author
        try:
            await author.edit(nick=None, reason=str(ctx.author))
        except discord.errors.Forbidden:
            return await ctx.send("💢 I can't reset your nickname.")
        
        await ctx.send(f"I've reset your nickname, {ctx.author.mention}.")

    @commands.group()
    async def announce(self, ctx):
        """Announcements"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @announce.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
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
    @commands.bot_has_permissions(embed_links=True)
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

    @commands.command()
    async def bmp(self, ctx, link: str):
        """Converts a .bmp image to .png"""
        #if link is None:
         #   if ctx.message.attachments:
        #        f = ctx.message.attachments
        #        if f.filename.lower().endswith('.bmp') and f.size <= 600000:
        #            image_bmp = await self.bot.aiogetbytes(f.url)
         #           image_final = self.finalize_image(image_bmp)
        #            await ctx.send(file=image_final)
        #        else: 
        #            return await ctx.send("This is not a `.bmp` file.")
        #    else:
         #       return await ctx.send(":x: Provide either a link or an attachment to your message"/
        #                              "so it can be converted.")
        try:
            image_bmp = await self.bot.aiogetbytes(link)
            img_final = self.finalize_image(image_bmp)
            filex = discord.File(img_final, filename=f"BMP conversion from {ctx.author}.png")
            await ctx.send(file=filex)
        except ValueError:
            return await ctx.send(":x: Provide a link to your message"/
                                  "so it can be converted.")






def setup(bot):
    bot.add_cog(Misc(bot))
