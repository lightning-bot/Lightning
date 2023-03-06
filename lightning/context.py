"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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
from contextlib import suppress
from typing import TYPE_CHECKING, Optional, Sequence, Union

import discord
import sanctum
from discord.ext import commands

from lightning.utils.helpers import request as make_request
from lightning.utils.helpers import ticker
from lightning.utils.ui import ConfirmationView

if TYPE_CHECKING:
    from lightning.bot import LightningBot

__all__ = ("LightningContext", "GuildContext")


class LightningContext(commands.Context):
    bot: LightningBot
    prefix: str
    command: commands.Command

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def tick(self, boolean: bool, *, send=True) -> Union[str, discord.Message]:
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

    async def confirm(self, message: str, *, delete_after=True, include_help_message=False) -> Optional[bool]:
        view = ConfirmationView(message, context=self, delete_message_after=delete_after,
                                include_help_message=include_help_message)
        await view.start()

        return view.value

    async def ask(self, question: str, *, timeout: int = 60) -> Optional[discord.Message]:
        """Prompts the member to send a message"""
        await self.send(question)

        def check(m):
            return m.channel == self.channel and m.author == self.author

        try:
            message = await self.bot.wait_for("message", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await self.send("Timed out while waiting for a response.")
            return

        return message

    async def send(self, content: Optional[str] = None, *,
                   tts: bool = False,
                   embed: Optional[discord.Embed] = None,
                   embeds: Optional[Sequence[discord.Embed]] = None,
                   file: Optional[discord.File] = None,
                   files: Optional[Sequence[discord.File]] = None,
                   stickers: Optional[Sequence[Union[discord.GuildSticker, discord.StickerItem]]] = None,
                   delete_after: Optional[float] = None,
                   nonce: Optional[Union[str, int]] = None,
                   allowed_mentions: Optional[discord.AllowedMentions] = None,
                   reference: Optional[Union[discord.Message, discord.MessageReference, discord.PartialMessage]] = None,
                   mention_author: Optional[bool] = None,
                   view: Optional[discord.ui.View] = None,
                   suppress_embeds: bool = False,
                   ephemeral: bool = False,
                   silent: bool = False) -> discord.Message:
        content = await self._prepare_send(content)
        return await super().send(content=content,
                                  tts=tts,
                                  embed=embed,
                                  embeds=embeds,
                                  file=file,
                                  files=files,
                                  stickers=stickers,
                                  delete_after=delete_after,
                                  nonce=nonce,
                                  allowed_mentions=allowed_mentions,
                                  reference=reference,
                                  mention_author=mention_author,
                                  view=view,
                                  suppress_embeds=suppress_embeds,
                                  ephemeral=ephemeral,
                                  silent=silent)

    async def _prepare_send(self, content: Optional[str] = None) -> Optional[str]:
        content = str(content) if content is not None else None
        if content and len(content) >= 2000:
            try:
                url = await self.bot.api.create_paste(content)
                content = f"Content too long: {url['full_url']}"
            except sanctum.HTTPException:
                content = "Content too long..."
        return content

    async def request(self, url, **kwargs) -> Union[dict, str, bytes]:
        return await make_request(url, self.bot.aiosession, **kwargs)


class GuildContext(LightningContext):
    guild: discord.Guild
    me: discord.Member
    author: discord.Member
