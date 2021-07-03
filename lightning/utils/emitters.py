"""
Lightning.py - A personal Discord bot
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

import aiohttp
import discord


class Emitter:
    """Base emitter"""
    def __init__(self, *, loop: asyncio.AbstractEventLoop = None):
        self.loop = loop or asyncio.get_event_loop()
        self._queue = asyncio.Queue()
        self._task = None

    def start(self) -> None:
        self._task = self.loop.create_task(self._run())

    @property
    def closed(self):
        return self._task.cancelled() if self._task else True

    def close(self) -> None:
        self._task.cancel()

    def running(self) -> bool:
        return not self.closed

    def get_task(self):
        return self._task

    async def _run(self):
        raise NotImplementedError


class WebhookEmbedEmitter(Emitter):
    """An emitter designed for webhooks sending embeds"""
    def __init__(self, url: str, *, session: aiohttp.ClientSession = None, **kwargs):
        self.session = session or aiohttp.ClientSession()
        self.webhook = discord.Webhook.from_url(url, session=self.session)
        super().__init__(**kwargs)

    async def put(self, embed: discord.Embed) -> None:
        await self._queue.put(embed)

    async def _run(self):
        while not self.closed:
            embed = await self._queue.get()
            embeds = [embed]
            await asyncio.sleep(5)

            size = self._queue.qsize()
            for _ in range(min(9, size)):
                embeds.append(self._queue.get_nowait())

            await self.webhook.send(embeds=embeds)


class TextChannelEmitter(Emitter):
    """An emitter designed for a text channel"""
    def __init__(self, channel: discord.TextChannel, **kwargs):
        super().__init__(**kwargs)
        self.channel = channel

    def start(self) -> None:
        super().start()
        self._task.set_name(f"textchannel-emitter-{self.channel.id}")

    async def put(self, *args, **kwargs):
        coro = self.channel.send(*args, **kwargs)
        await self._queue.put(coro)

    async def send(self, *args, **kwargs):
        """Alias function for TextChannelEmitter.put"""
        await self.put(*args, **kwargs)

    async def _run(self):
        while not self.closed:
            coro = await self._queue.get()

            try:
                await coro
            except discord.NotFound:
                self.close()
            except (asyncio.TimeoutError, aiohttp.ClientError, discord.HTTPException):
                pass

            # Rough estimate to wait before sending again without hitting ratelimits.
            # We may need to rethink this...
            await asyncio.sleep(0.7)
