# Lightning.py - The Successor to Lightning.js
# Copyright (C) 2019 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version

import discord
import random
from datetime import datetime
from discord.ext import commands
from utils.checks import is_staff_or_has_perms, has_staff_role
import io
import asyncio
import colorsys
from PIL import Image
from utils.converters import SafeSend


class Utility(commands.Cog):
    """Optionally helpful commands"""
    def __init__(self, bot):
        self.bot = bot

    def finalize_image(self, image):  # Image Save
        image_b = Image.open(io.BytesIO(image))
        image_file = io.BytesIO()
        image_b.save(image_file, format="png")
        image_file.seek(0)
        return image_file

    @commands.command(aliases=['say'])
    @commands.guild_only()
    @has_staff_role("Helper")
    async def speak(self, ctx, channel: discord.TextChannel, *, inp: SafeSend):
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
    @commands.cooldown(rate=1, per=60.0, type=commands.BucketType.channel)
    async def texttobinary(self, ctx, *, text: str):
        """Converts text to binary"""
        async with ctx.typing():
            msg = " ".join(f"{ord(i):08b}" for i in text)
            if len(msg) > 1985:
                link = await self.bot.haste(msg)
                msg = f"Output too big, see the haste {link}"
        await ctx.send(f"```{msg}```")

    @commands.command(aliases=['hastebin'])
    @commands.cooldown(rate=1, per=60.0, type=commands.BucketType.channel)
    async def pastebin(self, ctx, *, message: str):
        """Make a pastebin with your own message"""
        url = await self.bot.haste(message)
        await ctx.send(f"Here's your pastebin. {ctx.author.mention}\n{url}")

    @commands.command()
    @commands.cooldown(rate=1, per=250.0, type=commands.BucketType.channel)
    @is_staff_or_has_perms("Admin", manage_guild=True)
    async def archive(self, ctx, limit: int):
        """Archives the current channel's contents.
        Admins only!"""
        if limit > 750:  # Safe Value
            return await ctx.send("Too big! Lower the value!")
        log_t = f"Archive of {ctx.channel} (ID: {ctx.channel.id}) "\
                f"made on {datetime.utcnow()}\n\n\n"
        async with ctx.typing():
            async for log in ctx.channel.history(limit=limit):
                # .strftime('%X/%H:%M:%S') but no for now
                log_t += f"[{log.created_at}]: {log.author} - {log.clean_content}"
                if log.attachments:
                    for attach in log.attachments:
                        log_t += f"{attach.url}\n"
                else:
                    log_t += "\n"

        aiostring = io.StringIO()
        aiostring.write(log_t)
        aiostring.seek(0)
        aiofile = discord.File(aiostring, filename=f"{ctx.channel}_archive.txt")
        await ctx.send(file=aiofile)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(change_nickname=True)
    @commands.bot_has_permissions(change_nickname=True)
    async def setnick(self, ctx, *, nick: str = ""):
        """Set your own nickname.

        Clear your nickname by just sending .setnick"""
        author = ctx.author
        try:
            if nick:
                await author.edit(nick=nick, reason=str(ctx.author))
                msg = f"Successfully set nickname to {nick}"
            else:
                await author.edit(nick=None, reason=str(ctx.author))
                msg = "Successfully wiped your nickname!"
        except discord.errors.Forbidden:
            return await ctx.send("💢 I can't change your nickname.")

        await ctx.send(msg)

    @commands.command()
    @commands.guild_only()
    async def topic(self, ctx, *, channel: discord.TextChannel = None):
        """Quotes the channel topic."""
        if channel is None:
            channel = ctx.message.channel
        if channel.topic is None:
            return await ctx.send(f"{channel.mention} has no topic set!")
        embed = discord.Embed(title=f"Channel Topic for {channel}",
                              description=f"{channel.topic}",
                              color=discord.Color.dark_blue())
        await ctx.send(embed=embed)

    @commands.command(aliases=['bmptopng'])
    async def bmp(self, ctx, link=None):
        """Converts a .bmp image to .png"""
        if link is None:
            if ctx.message.attachments:
                f = ctx.message.attachments[0]
                if f.filename.lower().endswith('.bmp'):
                    image_bmp = await self.bot.aiogetbytes(f.url)
                    img_final = self.finalize_image(image_bmp)
                    filex = discord.File(img_final,
                                         filename=f"BMP conversion from {ctx.author}.png")
                    await ctx.send(file=filex)
                else:
                    return await ctx.send("This is not a `.bmp` file.")
            else:
                return await ctx.send(":x: Either provide an attachment or a link so it can be converted")
        else:
            if link.lower().endswith('.bmp'):
                try:
                    image_bmp = await self.bot.aiogetbytes(link)
                    img_final = self.finalize_image(image_bmp)
                    filex = discord.File(img_final, filename=f"BMP conversion from {ctx.author}.png")
                    await ctx.send(file=filex)
                except Exception:
                    return await ctx.send(":x: Provide a link to your message"
                                          "so it can be converted.")
            else:
                return await ctx.send("This is not a `.bmp` file.")

    @commands.group()
    async def announce(self, ctx):
        """Announcements"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @announce.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @has_staff_role("Moderator")
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
        title = msg.content  # Set the title

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
    @has_staff_role("Moderator")
    async def simple(self, ctx, channel: discord.TextChannel, *, text):
        """Make a simple announcement"""  # Basically the speak command, but mentions the author.
        await channel.send(f"Announcement from {ctx.author.mention}:\n\n{text}")

    @announce.command(aliases=['rcembed', 'colorembed'])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @has_staff_role("Moderator")
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
        title = msg.content  # Set the title

        await ctx.send(content='What would you like to set as the description?')
        try:
            msg = await self.bot.wait_for('message', timeout=300.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long. Bye')
        desc = msg.content

        msg = await ctx.send(content=f'Now sending the embed to {channel.mention}...')
        # Chooses a random color
        color_random = [int(x * 255) for x in colorsys.hsv_to_rgb(random.random(), 1, 1)]
        embed = discord.Embed(title=title, description=desc, colour=discord.Color.from_rgb(*color_random))
        embed.set_author(name=ctx.message.author, icon_url=ctx.message.author.avatar_url)
        embed.timestamp = msg.created_at
        await channel.send(embed=embed, content=None)
        return


def setup(bot):
    bot.add_cog(Utility(bot))
