"""
Lightning.py - A multi-purpose Discord bot
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

import io
from contextlib import suppress
from typing import Union

import discord
from discord.ext import commands

from lightning import errors
from lightning.utils.helpers import ConfirmationMenu, Emoji, haste
from lightning.utils.helpers import request as make_request
from lightning.utils.helpers import ticker


class LightningContext(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def tick(self, boolean: bool, *, send=True) -> Union[bool, discord.Message]:
        tick = ticker(boolean)

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
        resp = await ConfirmationMenu(self, message, delete_message_after=delete_after,
                                      confirmation_message=confirmation_message).prompt()
        return resp

    async def send(self, content=None, *args, **kwargs) -> discord.Message:
        if content:
            if len(content) > 2000:
                try:
                    mysturl = await haste(self.bot.aiosession, content)
                    content = f"Content too long: {mysturl}"
                except errors.LightningError:
                    fp = io.StringIO(content)
                    content = "Content too long..."
                    return await super().send(content, file=discord.File(fp, filename='message_too_long.txt'))
        return await super().send(content, *args, **kwargs)

    async def request(self, url, **kwargs) -> Union[dict, str, bytes]:
        return await make_request(url, self.bot.aiosession, **kwargs)
