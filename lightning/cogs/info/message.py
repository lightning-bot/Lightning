"""
Lightning.py - A Discord bot
Copyright (C) 2019-2022 LightSage

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

import json
from typing import TYPE_CHECKING

import discord

from lightning import LightningCog, group
from lightning.cogs.info.converters import Message, ReadableChannel
from lightning.errors import ChannelPermissionFailure, MessageNotFoundInChannel
from lightning.utils.helpers import message_id_lookup

if TYPE_CHECKING:
    from lightning import LightningContext


class MessageInfo(LightningCog):
    def message_info_embed(self, msg: discord.Message) -> discord.Embed:
        embed = discord.Embed(timestamp=msg.created_at)

        if hasattr(msg.author, 'nick') and msg.author.display_name != str(msg.author):
            author_name = f"{msg.author.display_name} ({msg.author})"
        else:
            author_name = msg.author

        embed.set_author(name=author_name, icon_url=msg.author.display_avatar.url)

        if msg.guild:
            embed.set_footer(text=f"\N{NUMBER SIGN}{msg.channel}")
        else:
            embed.set_footer(text=msg.channel)

        description = msg.content
        if msg.attachments:
            attach_urls = [
                f'[{attachment.filename}]({attachment.url})'
                for attachment in msg.attachments
            ]

            description += '\n\N{BULLET} ' + '\n\N{BULLET} '.join(attach_urls)
        if msg.embeds:
            description += "\n \N{BULLET} Message has an embed"
        embed.description = description

        if hasattr(msg.author, 'color'):
            embed.color = msg.author.color

        return embed

    @group(invoke_without_command=True, usage="<message>", require_var_positional=True)
    async def quote(self, ctx: LightningContext, *message) -> None:
        """Quotes a message.

        You can pass either the message ID and channel ID (i.e {prefix}quote <message_id> <channel>) \
        or you can pass a message link"""
        message_id, channel = await Message().convert(ctx, message)
        msg = discord.utils.get(ctx.bot.cached_messages, id=message_id)
        if msg is None:
            try:
                msg: discord.Message = await message_id_lookup(ctx.bot, channel.id, message_id)
            except discord.NotFound:
                raise MessageNotFoundInChannel(message_id, channel)
            except discord.Forbidden:
                raise ChannelPermissionFailure(f"I don't have permission to view {channel.mention}.")
        else:
            await ReadableChannel().convert(ctx, str(msg.channel.id))

        embed = self.message_info_embed(msg)
        view = discord.ui.View().add_item(discord.ui.Button(label="Jump to message", url=msg.jump_url))
        await ctx.send(embed=embed, view=view)

    @quote.command(name="raw", aliases=['json'], require_var_positional=True)
    async def msg_raw(self, ctx: LightningContext, *message) -> None:
        """Shows raw JSON for a message."""
        message_id, channel = await Message().convert(ctx, message)
        try:
            message = await ctx.bot.http.get_message(channel.id, message_id)
        except discord.NotFound:
            raise MessageNotFoundInChannel(message_id, channel)

        await ctx.send(f"```json\n{json.dumps(message, indent=2, sort_keys=True)}```")
