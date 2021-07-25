"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation at version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio
from datetime import datetime
from io import StringIO

import discord
from discord.ext import commands
from discord.ext import menus as dmenus

from lightning import (Flag, FlagCommand, LightningBot, LightningCog,
                       LightningContext, command, group)
from lightning.converters import ReadableChannel, Snowflake, SnowflakeDT
from lightning.utils import helpers
from lightning.utils.time import format_timestamp


class EmbedBuilderMenu(dmenus.Menu):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.embed = discord.Embed()

    async def send_initial_message(self, ctx, channel):
        return await channel.send("Welcome to the interactive embed builder menu. To get started, press the "
                                  "\N{INFORMATION SOURCE} button.")

    async def wait_for_message(self):
        def check(m):
            return m.author.id == self.ctx.author.id and m.channel.id == self.ctx.channel.id
        try:
            msg = await self.ctx.bot.wait_for('message', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await self.ctx.send("Timed out waiting for a message.")
            return
        return msg

    @dmenus.button("\N{MEMO}")
    async def set_description(self, payload):
        """Sets a description for the embed"""
        await self.message.edit(content="Send the message you want to add as a description")
        msg = await self.wait_for_message()
        self.embed.description = msg.content

    @dmenus.button("\N{LABEL}")
    async def set_title(self, payload):
        """Sets the title for the embed"""
        await self.message.edit(content="Send the message you want to add as a title.\n**Limits**: Text can only be 256"
                                        "characters or less")
        msg = await self.wait_for_message()

        if len(msg.content) > 256:
            await self.ctx.send("Title can only be 256 characters or less.")
            return

        self.embed.title = msg.content

    @dmenus.button("\N{INFORMATION SOURCE}\ufe0f", position=dmenus.Last(3))
    async def info_page(self, payload) -> None:
        """shows you this message"""
        messages = []
        for emoji, button in self.buttons.items():
            messages.append(f'{str(emoji)} {button.action.__doc__}')

        embed = discord.Embed(title="Help", color=discord.Color.blurple())
        embed.clear_fields()
        embed.description = '\n'.join(messages)
        await self.message.edit(content=None, embed=embed)

    @dmenus.button("\N{CHEQUERED FLAG}")
    async def build(self, payload):
        """Sends the embed"""
        await self.ctx.send(embed=self.embed)
        self.stop()


ARCHIVE_FLAGS = [Flag("--reverse", "-r", help="Reverses the messages to oldest message first", is_bool_flag=True),
                 Flag("--limit", converter=int, default=50, help="The limit of messages to get"),
                 Flag("--ignore-bots", is_bool_flag=True, help="Ignores messages from bots"),
                 Flag("--user", converter=discord.User, help="The user to archive messages from"),
                 Flag("--before", converter=Snowflake, help="Archives messages before a message ID"),
                 Flag("--after", converter=Snowflake, help="Archives messages after a message ID"),
                 Flag("--channel", "-c", converter=ReadableChannel, help="The channel to archive messages from")]


class Misc(LightningCog):
    """Commands that might be helpful..."""

    @command(enabled=False, hidden=True)
    async def embedbuilder(self, ctx: LightningContext) -> None:
        """WIP embed builder command"""
        em = EmbedBuilderMenu()
        await em.start(ctx)

    @command()
    @commands.bot_has_permissions(add_reactions=True)
    async def poll(self, ctx: LightningContext, *, question: str) -> None:
        """Creates a simple poll with thumbs up, thumbs down, and shrug as reactions"""
        msg = await ctx.send(f"{ctx.author.mention} asks:\n{question}")
        await asyncio.gather(msg.add_reaction("\N{THUMBS UP SIGN}"), msg.add_reaction("\N{THUMBS DOWN SIGN}"),
                             msg.add_reaction("\N{SHRUG}"))

    @group(invoke_without_command=True)
    @commands.bot_has_permissions(read_message_history=True)
    @commands.cooldown(rate=3, per=150.0, type=commands.BucketType.guild)
    async def archive(self, ctx: LightningContext, limit: int,
                      channel: ReadableChannel = commands.default.CurrentChannel) -> None:
        """Archives a channel's contents to a text file."""
        if limit > 250:
            await ctx.send("You can only archive 250 messages.")
            return

        async with ctx.typing():
            fp = await helpers.archive_messages(channel, limit)

        await ctx.send(file=fp)

    @archive.command(cls=FlagCommand, name="custom", flags=ARCHIVE_FLAGS)
    @commands.bot_has_permissions(read_message_history=True)
    @commands.cooldown(rate=3, per=150.0, type=commands.BucketType.guild)
    async def archive_custom(self, ctx: LightningContext, **flags):
        """An advanced archive command

        This command uses "command line" syntax."""
        args = {'limit': flags['limit']}

        if flags['before']:
            args['before'] = flags['before']

        if flags['after']:
            args['after'] = flags['after']

        channel: discord.TextChannel = flags['channel'] or ctx.channel

        messages = []
        async for msg in channel.history(**args):
            if flags['user'] and msg.author.id != flags['user'].id:
                continue

            if flags['ignore_bots'] and msg.author.bot:
                continue

            messages.append(f"[{msg.created_at}]: {msg.author} - {msg.clean_content}")

            if msg.embeds:
                messages.append(f"Embed data: {[e.to_dict() for e in msg.embeds]}")

            if msg.attachments:
                for attachment in msg.attachments:
                    messages.append(f"{attachment.url}\n")
            else:
                messages.append("\n")

        if not messages:
            await ctx.send("0 messages met your conditions. Try a bigger limit(?)")
            return

        if flags['reverse']:
            messages.reverse()

        text = f"Archive of {channel} (ID: {channel.id}) made at {datetime.utcnow()}\nConditions: {dict(flags)}"\
               f"\n\n\n{''.join(messages)}"

        _bytes = StringIO()
        _bytes.write(text)
        _bytes.seek(0)

        await ctx.send(file=discord.File(_bytes, filename="message_archive.txt"))

    @command()
    @commands.guild_only()
    async def topic(self, ctx: LightningContext, *,
                    channel: ReadableChannel = commands.default.CurrentChannel) -> None:
        """Quotes a channel's topic"""
        if channel.topic is None or channel.topic == "":
            await ctx.send(f"{channel.mention} has no topic set!")
            return

        embed = discord.Embed(description=channel.topic,
                              color=discord.Color.dark_blue())
        embed.set_footer(text=f"Showing topic for #{str(channel)}")
        await ctx.send(embed=embed)

    @command()
    async def snowflake(self, ctx: LightningContext, snowflake: SnowflakeDT) -> None:
        """Tells you when a snowflake was created"""
        fmt = f"{discord.utils.format_dt(snowflake, style='f')}\n{format_timestamp(snowflake)}"
        await ctx.send(fmt)


def setup(bot: LightningBot):
    bot.add_cog(Misc(bot))
