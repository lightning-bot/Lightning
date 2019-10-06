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
from utils.converters import SafeSend, ReadableChannel
import asyncpg


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

    @commands.group(invoke_without_command=True)
    async def snipe(self, ctx, channel: ReadableChannel = None):
        """Snipes the last deleted message in the specified channel."""
        if channel is None:
            channel = ctx.channel
        query = """SELECT * FROM sniped_messages
                   WHERE guild_id=$1
                   AND channel_id=$2;
                """
        sniped_msg = await self.bot.db.fetchrow(query, ctx.guild.id, channel.id)
        if channel.is_nsfw() is True and ctx.channel.is_nsfw() is False:
            return await ctx.send("No sniping NSFW outside of a NSFW channel.")
        if channel.id in await self.get_snipe_channels(ctx.guild.id):
            return await ctx.send(f"{channel.mention} is blacklisted and cannot be sniped!")
        if not sniped_msg:
            return await ctx.send("Couldn't find anything to snipe")
        user = self.bot.get_user(sniped_msg['user_id'])
        embed = discord.Embed(title=f"{user} said",
                              description=sniped_msg['message'],
                              timestamp=sniped_msg['timestamp'])
        embed.set_footer(text=f"#{channel} in {ctx.guild}")
        await ctx.send(embed=embed)

    @snipe.command(name="view-settings")
    async def snipe_settings_v(self, ctx):
        """Views snipe settings"""
        query = """SELECT * FROM snipe_settings WHERE guild_id=$1;"""
        settings = await self.bot.db.fetchrow(query, ctx.guild.id)
        if not settings:
            return await ctx.send("This guild has no channels blacklisted from sniping!")
        if settings['channel_ids']:
            embed = discord.Embed(title="Snipe Settings", color=0xf74b06)
            channels = []
            for r in settings['channel_ids']:
                ch = discord.utils.get(ctx.guild.text_channels, id=r)
                channels.append(ch.mention)
            embed.add_field(name="Blacklisted Channels", value="\n".join(channels))
        else:
            return await ctx.send(f"Nothing currently blacklisted!")
        await ctx.send(embed=embed)

    async def get_snipe_channels(self, guild_id: int):
        query = """SELECT channel_ids
                   FROM snipe_settings
                   WHERE guild_id=$1;
                """
        snipe_channels = await self.bot.db.fetchval(query, guild_id)
        if snipe_channels:
            return snipe_channels
        else:
            return []

    async def get_snipe_users(self, guild_id: int):
        query = """SELECT user_ids FROM snipe_settings WHERE guild_id=$1"""
        ret = await self.bot.db.fetchval(query, guild_id)
        if ret:
            return ret
        else:
            return []

    @snipe.group(name="blacklist")
    @is_staff_or_has_perms("Admin", manage_guild=True)
    async def blacklisted(self, ctx):
        """Manages the snipe blacklist."""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @blacklisted.command(name="add-channel", aliases=['addchannel'])
    @is_staff_or_has_perms("Admin", manage_guild=True)
    async def snipe_settings_add(self, ctx, *, channel: discord.TextChannel = None):
        """Adds a channel that cannot be sniped.

        In order to use this command, you must either have
        Manage Server permission or a role that
        is assigned as an Admin or above in the bot."""
        if channel is None:
            channel = ctx.channel
        add_query = """INSERT INTO snipe_settings (guild_id, channel_ids)
                       VALUES ($1, $2::bigint[])
                       ON CONFLICT (guild_id)
                       DO UPDATE SET channel_ids = EXCLUDED.channel_ids;
                    """
        snipe_channels = await self.get_snipe_channels(ctx.guild.id)
        if channel.id in snipe_channels:
            return await ctx.send(f"{channel.mention} is already added as a blacklisted channel.")
        snipe_channels.append(channel.id)
        await self.bot.db.execute(add_query, ctx.guild.id, snipe_channels)
        await ctx.send(f"Added {channel.mention} to the list of blacklisted channels.")

    @blacklisted.command(name="remove-channel", aliases=['deletechannel', 'removechannel'])
    @is_staff_or_has_perms("Admin", manage_guild=True)
    async def snipe_settings_rmo(self, ctx, *, channel: discord.TextChannel = None):
        """Removes a channel that was previously blacklisted
        from being sniped.

        In order to use this command, you must either have
        Manage Server permission or a role that
        is assigned as an Admin or above in the bot."""
        if channel is None:
            channel = ctx.channel
        query = """INSERT INTO snipe_settings (guild_id, channel_ids)
                   VALUES ($1, $2::bigint[])
                   ON CONFLICT (guild_id)
                   DO UPDATE SET channel_ids = EXCLUDED.channel_ids;
                """
        snipe_channels = await self.get_snipe_channels(ctx.guild.id)
        if channel.id not in snipe_channels:
            return await ctx.send(f"{channel.mention} was never blacklisted!")
        snipe_channels.remove(channel.id)
        await self.bot.db.execute(query, ctx.guild.id, snipe_channels)
        await ctx.send(f"\N{THUMBS UP SIGN} {channel.mention} is now unblacklisted from sniping.")

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        ignored = await self.get_snipe_channels(message.guild.id)
        if message.channel.id in ignored:
            return
        # if message.author.id in ignored:
        #    return
        content = message.content
        if message.attachments:
            content = str(message.attachments[0].proxy_url)
        if message.embeds:
            if message.embeds[0].description:
                content = message.embeds[0].description
            else:
                content = f"{message.content}\n\n**Message contained an embed.**"
        query = """INSERT INTO sniped_messages
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (channel_id)
                   DO UPDATE SET
                   channel_id = EXCLUDED.channel_id,
                   guild_id = EXCLUDED.guild_id,
                   message = EXCLUDED.message,
                   user_id = EXCLUDED.user_id,
                   timestamp = EXCLUDED.timestamp
                """
        try:
            await self.bot.db.execute(query, message.guild.id, message.channel.id,
                                      content, message.author.id,
                                      datetime.fromisoformat(message.created_at.isoformat()))
        except asyncpg.DataError:
            pass

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
        if limit > 100:  # Safe Value
            return await ctx.send("You can only archive 100 messages!")
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
    @has_staff_role("Moderator")
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
