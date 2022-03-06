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

import discord

from lightning import LightningCog, LightningContext, group
from lightning.cogs.info.converters import Message
from lightning.converters import ReadableChannel
from lightning.errors import ChannelPermissionFailure, MessageNotFoundInChannel
from lightning.utils.helpers import message_id_lookup


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
        description += f"\n\n[Jump to message]({msg.jump_url})"
        if msg.embeds:
            description += "\n \N{BULLET} Message has an embed"
        embed.description = description

        if hasattr(msg.author, 'color'):
            embed.color = msg.author.color

        return embed

    @group(aliases=['messageinfo', 'msgtext'], invoke_without_command=True)
    async def quote(self, ctx: LightningContext, *message) -> None:
        """Quotes a message"""
        message_id, channel = await Message().convert(ctx, message)
        msg = discord.utils.get(ctx.bot.cached_messages, id=message_id)
        if msg is None:
            try:
                msg = await message_id_lookup(ctx.bot, channel.id, message_id)
            except discord.NotFound:
                raise MessageNotFoundInChannel(message_id, channel)
            except discord.Forbidden:
                raise ChannelPermissionFailure(f"I don't have permission to view {channel.mention}.")
        else:
            await ReadableChannel().convert(ctx, str(msg.channel.id))

        embed = self.message_info_embed(msg)
        await ctx.send(embed=embed)

    @quote.command(name="raw", aliases=['json'])
    async def msg_raw(self, ctx: LightningContext, *message) -> None:
        """Shows raw JSON for a message."""
        message_id, channel = await Message().convert(ctx, message)
        try:
            message = await ctx.bot.http.get_message(channel.id, message_id)
        except discord.NotFound:
            raise MessageNotFoundInChannel(message_id, channel)

        await ctx.send(f"```json\n{json.dumps(message, indent=2, sort_keys=True)}```")
