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

import datetime
import io
import logging
import typing

import aiohttp
import discord
from discord.ext import commands

from lightning import errors

log = logging.getLogger(__name__)


async def archive_messages(channel: discord.TextChannel, limit: int, *, filename=None) -> discord.File:
    """Makes a txt file containing the limit of messages specified.

    Parameters
    ----------
    ctx : Context
        The context that invoked the command.
    limit : int
        How many messages to search for
    filename : None, Optional
        Optional file name

    Returns
    -------
    :class:discord.File
        A .txt file containing the messages
    """
    logtext = f"Archive of {channel} (ID: {channel.id}) "\
              f"made on {datetime.datetime.utcnow()}\n\n\n"
    async for log in channel.history(limit=limit):
        logtext += f"[{log.created_at}]: {log.author} - {log.clean_content}"
        if log.attachments:
            for attach in log.attachments:
                logtext += f"{attach.url}\n"
        else:
            logtext += "\n"
    txtlog = io.StringIO()
    txtlog.write(logtext)
    txtlog.seek(0)
    return discord.File(txtlog, filename=filename or f"message_archive_{str(channel)}.txt")


async def message_id_lookup(bot, channel_id: int, message_id: int):
    """Helper function that performs a message lookup.

    It is preferred that you handle permissions before using this function.

    If the channel isn't found, raises :class:`ChannelNotFound`.
    If some exception happens, raises :class:`LightningError`.
    If the message isn't found, returns ``None``.

    Parameters
    ----------
    bot : Bot
        The bot.
    channel_id : int
        The ID of channel that the message belongs to.
    message_id : int
        The ID of the message that is being looked up.

    Returns
    -------
    :class:`discord.Message`
        The message object.

    Raises
    ------
    commands.BotMissingPermissions
        Raised when bot is missing permissions to use the history endpoint.
    errors.ChannelNotFound
        Raised when the channel containing the message was deleted
    errors.LightningError
        Raised when some exception happens.
    """
    channel = bot.get_channel(channel_id)
    if channel is None:
        raise errors.ChannelNotFound("Channel was deleted.")

    try:
        msg = await channel.fetch_message_fast(message_id)
    except discord.HTTPException:
        raise errors.LightningError("Somehow failed to find that message. Try again later?")
    except discord.Forbidden:
        raise commands.BotMissingPermissions(['read_message_history'])

    return msg


async def webhook_send(session: aiohttp.ClientSession, webhook_id: int, token: str, message=None,
                       **kwargs) -> typing.Optional[discord.Message]:
    """Sends a message through a webhook

    Parameters
    ----------
    session : aiohttp.ClientSession
        The session to use.
    webhook_id : int
        The webhook's ID
    token : str
        Token of the webhook
    message : None, optional
        The content of the message to send
    **kwargs
        Keyword arguments that are passed to discord.Webhook.send()

    Returns
    -------
    Optional[discord.Message]
        Returns a message object if the wait kwarg is passed
    """
    webhook = discord.Webhook.partial(webhook_id, token, adapter=discord.AsyncWebhookAdapter(session))
    try:
        await webhook.send(message, **kwargs)
    except discord.NotFound:
        return None


async def dm_user(user: typing.Union[discord.User, discord.Member], message: str = None, **kwargs):
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
    except (AttributeError, discord.HTTPException, discord.Forbidden):
        return False


class Emoji:
    greentick = "<:greenTick:613702930444451880>"
    redtick = "<:redTick:613703043283681290>"
    member_leave = "<:member_leave:613363354357989376>"
    member_join = "<:member_join:613361413272109076>"
    python = "<:python:605592693267103744>"
    dpy = "<:dpy:617883851162779648>"
    postgres = "<:postgres:617886426318635015>"
    # Presence emojis
    do_not_disturb = "<:dnd:572962188134842389>"
    online = "<:online:572962188114001921>"
    idle = "<:idle:572962188201820200>"
    offline = "<:offline:572962188008882178>"
    numbers = ('1\N{combining enclosing keycap}',
               '2\N{combining enclosing keycap}',
               '3\N{combining enclosing keycap}',
               '4\N{combining enclosing keycap}',
               '5\N{combining enclosing keycap}',
               '6\N{combining enclosing keycap}',
               '7\N{combining enclosing keycap}',
               '8\N{combining enclosing keycap}',
               '9\N{combining enclosing keycap}',
               '\N{KEYCAP TEN}')


class BetterUserObject(discord.Object):
    def __init__(self, id):
        super().__init__(id)

    @property
    def mention(self):
        return '<@!%s>' % self.id

    def __str__(self):
        return str(self.id)


async def request(url, session: aiohttp.ClientSession, *, timeout=180, method: str = "GET", return_text=False,
                  **kwargs) -> typing.Union[dict, str, bytes]:
    async with session.request(method, url, timeout=timeout, **kwargs) as resp:
        if resp.status == 429:
            log.info(f"Ratelimited while requesting {url}")
            raise errors.HTTPRatelimited(resp)

        # TODO: Make it better

        if 300 > resp.status >= 200:
            if resp.headers['Content-Type'] == "application/json":
                return await resp.json()
            elif return_text is True:
                return await resp.text()
            else:
                return await resp.read()
        else:
            raise errors.HTTPException(resp)
