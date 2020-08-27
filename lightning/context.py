"""
Lightning.py - A multi-purpose Discord bot
Copyright (C) 2020 - LightSage

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

import io
from contextlib import suppress
from typing import Union

import discord
from discord.ext import commands

from lightning import errors
from lightning.utils import http
from lightning.utils.helpers import Emoji
from lightning.utils.menus import Confirmation


class LightningContext(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def tick(self, boolean: bool, *, send=True) -> Union[bool, discord.Message]:
        if boolean:
            tick = Emoji.greentick
        else:
            tick = Emoji.redtick

        if send:
            return await self.send(tick)
        else:
            return tick

    async def emoji_send(self, emoji: discord.Emoji) -> None:
        """Attempts to send the specified emote. If failed, reacts."""
        with suppress(discord.HTTPException):
            try:
                await self.message.channel.send(emoji)
            except discord.Forbidden:
                await self.message.add_reaction(emoji)

    async def prompt(self, message: str, *, delete_after=False, confirmation_message=True) -> bool:
        resp = await Confirmation(self, message, delete_message_after=delete_after,
                                  confirmation_message=confirmation_message).prompt()
        return resp

    async def send(self, content=None, *args, **kwargs) -> discord.Message:
        if content:
            if len(content) > 2000:
                try:
                    mysturl = await http.haste(self.bot.aiosession, content)
                    content = f"Content too long: {mysturl}"
                except errors.LightningError:
                    fp = io.StringIO(content)
                    content = "Content too long..."
                    return await super().send(content, file=discord.File(fp, filename='message_too_long.txt'))
        return await super().send(content, *args, **kwargs)
