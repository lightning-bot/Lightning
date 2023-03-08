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

import asyncio
import logging
from typing import Optional

import aiohttp
import discord

log = logging.getLogger(__name__)


class Emitter:
    """Base emitter"""
    def __init__(self, *, task_name=None):
        self.loop = asyncio.get_event_loop()
        self._queue = asyncio.Queue()
        self._task = None
        self._task_name: Optional[str] = task_name

    def start(self) -> None:
        self._task = self.loop.create_task(self.emit_loop(), name=self._task_name)

    @property
    def closed(self):
        """Boolean indicator whether the emitter is closed or running."""
        return self._task.cancelled() if self._task else True

    def close(self) -> None:
        """
        Closes the emitter loop
        """
        self._task.cancel()

    def running(self) -> bool:
        return not self.closed

    def get_task(self) -> Optional[asyncio.Task]:
        """Gets the underlying task for the emitter

        Returns
        -------
        Optional[asyncio.Task]
            The task object created if ran else None
        """
        return self._task

    async def emit_loop(self):
        try:
            await self._emit()
        except Exception as e:
            log.exception("An exception occurred during the emit loop", exc_info=e)

    async def _emit(self):
        """The underlying function of what the emitter will do.
        Subclasses should override this method"""
        raise NotImplementedError


class WebhookEmbedEmitter(Emitter):
    """An emitter designed for webhooks sending embeds"""
    def __init__(self, url: str, *, session: aiohttp.ClientSession = None):
        self.session = session or aiohttp.ClientSession()
        self.webhook = discord.Webhook.from_url(url, session=self.session)
        super().__init__()

    async def put(self, embed: discord.Embed) -> None:
        await self._queue.put(embed)

    async def _emit(self):
        while not self.closed:
            embed = await self._queue.get()
            embeds = [embed]
            await asyncio.sleep(5)

            size = self._queue.qsize()
            embeds.extend(self._queue.get_nowait() for _ in range(min(9, size)))
            await self.webhook.send(embeds=embeds)


class TextChannelEmitter(Emitter):
    """An emitter designed for a text channel"""
    def __init__(self, channel: discord.TextChannel):
        super().__init__(task_name=f"textchannel-emitter-{channel.id}")
        self.channel = channel

    async def put(self, content=None, **kwargs):
        await self._queue.put({'content': content, **kwargs})

    async def send(self, *args, **kwargs):
        """Alias function for TextChannelEmitter.put"""
        await self.put(*args, **kwargs)

    async def _emit(self):
        while not self.closed:
            msg = await self._queue.get()

            try:
                await self.channel.send(**msg)
            except discord.NotFound:
                self.close()
            except (asyncio.TimeoutError, aiohttp.ClientError, discord.HTTPException):
                pass

            # Rough estimate to wait before sending again without hitting ratelimits.
            # We may need to rethink this...
            await asyncio.sleep(0.7)
