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
import asyncio
import json
import logging
import subprocess
from typing import Optional, Union

import aiohttp
import asyncpg
import discord

from lightning import errors
from lightning.constants import Emoji

log = logging.getLogger(__name__)


async def dm_user(user: Union[discord.User, discord.Member], message: Optional[str] = None, **kwargs):
    """Sends a message to a user and handles errors

    Parameters
    ----------
    user : typing.Union[discord.User, discord.Member]
        The user you are sending the message
    message : str, Optional
        The message content
    **kwargs
        Optional kwargs that are passed into `discord.User.send`

    Returns
    -------
    bool
        Whether the message was successfully sent to the user or not.
    """
    try:
        await user.send(message, **kwargs)
        return True
    except (AttributeError, discord.HTTPException):
        return False


def ticker(boolean: bool) -> str:
    return Emoji.greentick if boolean else Emoji.redtick


class UserObject(discord.Object):
    def __init__(self, id):
        super().__init__(id)

    @property
    def mention(self):
        return f'<@!{self.id}>'

    def __str__(self):
        return str(self.id)


async def request(url, session: aiohttp.ClientSession, *, timeout=180, method: str = "GET", return_text=False,
                  **kwargs) -> Union[dict, str, bytes]:
    async with session.request(method, url, timeout=timeout, **kwargs) as resp:
        if resp.status == 429:
            log.info(f"Ratelimited while requesting {url}")
            raise errors.HTTPRatelimited(resp)

        # TODO: Make it better
        if resp.status == 404:
            log.info(f"404 while requesting {url}")
            raise errors.HTTPException(resp)

        if 300 > resp.status >= 200:
            if return_text is True:
                return await resp.text()

            try:
                return await resp.json()
            except aiohttp.ContentTypeError:
                return await resp.read()
        else:
            raise errors.HTTPException(resp)


async def run_in_shell(command: str):
    try:
        pipe = asyncio.subprocess.PIPE
        process = await asyncio.create_subprocess_shell(command,
                                                        stdout=pipe,
                                                        stderr=pipe)
        stdout, stderr = await process.communicate()
    except NotImplementedError:
        process = subprocess.Popen(command, shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
    return stdout.decode('utf-8'), stderr.decode('utf-8')


async def create_pool(dsn: str, **kwargs) -> asyncpg.Pool:
    """Creates a connection pool with type codecs for json and jsonb"""

    async def init(connection: asyncpg.Connection):
        await connection.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
        await connection.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')

    return await asyncpg.create_pool(dsn, init=init, **kwargs)


async def safe_delete(message) -> bool:
    """Helper function to safely delete a message.

    This is just a try/except.

    Returns
    -------
    bool
        An indicator whether the message was successfully deleted or not."""
    try:
        await message.delete()
        return True
    except discord.HTTPException:
        return False
