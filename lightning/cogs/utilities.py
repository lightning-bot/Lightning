"""
Lightning.py - A Discord bot
Copyright (C) 2019-2024 LightSage

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
from __future__ import annotations

import asyncio
from datetime import timedelta
from io import StringIO
from typing import TYPE_CHECKING, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from lightning import (Flag, GuildContext, HybridFlagCommand, LightningCog,
                       command, hybrid_command)
from lightning.converters import Snowflake, SnowflakeDT
from lightning.utils.checks import hybrid_guild_permissions
from lightning.utils.time import format_timestamp

if TYPE_CHECKING:
    from lightning import LightningBot, LightningContext

ARCHIVE_FLAGS = [Flag("--reverse", "-r", help="Reverses the messages to oldest message first", is_bool_flag=True),
                 Flag("--limit", converter=int, default=50, help="The limit of messages to get"),
                 Flag("--ignore-bots", is_bool_flag=True, help="Ignores messages from bots"),
                 Flag("--user", converter=discord.User, help="The user to archive messages from"),
                 Flag("--before", converter=Snowflake, help="Archives messages before a message ID"),
                 Flag("--after", converter=Snowflake, help="Archives messages after a message ID"),
                 Flag("--channel", "-c", converter=Union[discord.TextChannel, discord.Thread],
                      help="The channel to archive messages from")]


class Utilities(LightningCog):
    """Commands that might be helpful"""

    @hybrid_command()
    @commands.bot_has_permissions(create_polls=True)
    @hybrid_guild_permissions(create_polls=True)
    @app_commands.describe(hours="The interval for the poll (in hours)")
    async def poll(self, ctx: LightningContext, hours: Optional[commands.Range[int, 1, 744]], *, question: str):
        """
        Creates a simple poll with thumbs up, thumbs down, and shrug as a Discord poll.

        If no hours are given, the poll will end in 24 hours by default.
        """
        hours = 24 if hours is None else hours

        poll = discord.Poll(question, duration=timedelta(hours=hours))
        poll.add_answer(text="Yes", emoji="\N{THUMBS UP SIGN}")
        poll.add_answer(text="Maybe", emoji="\N{SHRUG}")
        poll.add_answer(text="No", emoji="\N{THUMBS DOWN SIGN}")

        await ctx.send(poll=poll)

    @hybrid_command()
    @commands.bot_has_permissions(add_reactions=True)
    async def rpoll(self, ctx: LightningContext, *, question: str) -> None:
        """Creates a simple reaction poll with thumbs up, thumbs down, and shrug as reactions"""
        msg = await ctx.send(f"{ctx.author.mention} asks:\n{question}")
        await asyncio.gather(msg.add_reaction("\N{THUMBS UP SIGN}"), msg.add_reaction("\N{THUMBS DOWN SIGN}"),
                             msg.add_reaction("\N{SHRUG}"))

    @hybrid_command(cls=HybridFlagCommand, name="archive", flags=ARCHIVE_FLAGS, flag_consume_rest=False)
    @commands.bot_has_permissions(read_message_history=True)
    @commands.guild_only()
    @app_commands.guild_only()
    @commands.cooldown(rate=3, per=150.0, type=commands.BucketType.guild)
    async def archive_custom(self, ctx: GuildContext, *, flags):
        """An advanced message archive command

        This command uses "command line" syntax."""
        args = {'limit': flags['limit']}

        if flags['before']:
            args['before'] = flags['before']

        if flags['after']:
            args['after'] = flags['after']

        channel: Union[discord.TextChannel, discord.Thread] = flags['channel'] or ctx.channel

        if channel.permissions_for(ctx.author).read_message_history is False:
            await ctx.send("You can't archive messages from that channel!")
            return

        if channel.permissions_for(ctx.me).read_message_history is False:
            await ctx.send("I can't archive messages from that channel. "
                           "Please give me Read Message History permissions in that channel")
            return

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

        text = f"Archive of {channel} (ID: {channel.id}) made at {discord.utils.utcnow()}\nConditions: {vars(flags)}"\
               f"\n\n\n{''.join(messages)}"

        _bytes = StringIO(text)
        _bytes.seek(0)

        await ctx.send(file=discord.File(_bytes, filename="message_archive.txt"))

    @command()
    async def snowflake(self, ctx: LightningContext, *snowflakes: SnowflakeDT) -> None:
        """Tells you when a snowflake(s) was created"""
        await ctx.send("\n".join([f"{discord.utils.format_dt(snowflake)}\n{format_timestamp(snowflake)}"
                                  for snowflake in snowflakes]))


async def setup(bot: LightningBot):
    await bot.add_cog(Utilities(bot))
