"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

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

import logging
from typing import TYPE_CHECKING, Dict, Iterable, Optional

from cryptography.fernet import Fernet, InvalidToken

if TYPE_CHECKING:
    from lightning import LightningBot

log = logging.getLogger(__name__)

# Message content that is tracked for AutoMod should never be cached for longer than a day.
MAX_CONTENT_TTL = 86400

_fernet: Optional[Fernet] = None


def _get_fernet(bot: LightningBot) -> Fernet:
    """Returns a Fernet instance built from the configured key.

    If no key is configured, a key is generated in-memory. This means that content
    encrypted before a restart will not be decryptable afterwards, which is acceptable
    given this cache is short-lived and non-critical."""
    global _fernet
    if _fernet is not None:
        return _fernet

    key = bot.config.tokens.automod_encryption_key
    if not key:
        log.warning("No automod_encryption_key configured, generating a temporary one. "
                    "Cached AutoMod message content will not survive a restart.")
        key = Fernet.generate_key()
    elif isinstance(key, str):
        key = key.encode()

    _fernet = Fernet(key)
    return _fernet


def _content_key(channel_id: int, message_id: int) -> str:
    return f"lightning:automod:message-content:{channel_id}:{message_id}"


async def store_message_content(bot: LightningBot, channel_id: int, message_id: int, content: str,
                                ttl_seconds: int) -> None:
    """Encrypts and caches a message's content in Redis for a limited amount of time.

    Parameters
    ----------
    bot : LightningBot
        The bot instance
    channel_id : int
        The id of the channel the message was sent in
    message_id : int
        The id of the message
    content : str
        The message content to cache
    ttl_seconds : int
        How long the content should be cached for, in seconds. This is always capped at
        one day (86400 seconds).
    """
    if not content:
        return

    fernet = _get_fernet(bot)
    token = fernet.encrypt(content.encode())
    ttl = min(ttl_seconds, MAX_CONTENT_TTL)
    await bot.redis_pool.set(_content_key(channel_id, message_id), token, ex=ttl)


async def get_message_contents(bot: LightningBot, tracked_ids: Iterable[str]) -> Dict[str, str]:
    """Fetches and decrypts cached message content for the given tracked message ids.

    Parameters
    ----------
    bot : LightningBot
        The bot instance
    tracked_ids : Iterable[str]
        An iterable of "channel_id:message_id" strings

    Returns
    -------
    Dict[str, str]
        A mapping of "channel_id:message_id" to the decrypted message content. Entries
        that expired or were never cached are omitted.
    """
    tracked_ids = list(tracked_ids)
    if not tracked_ids:
        return {}

    fernet = _get_fernet(bot)
    keys = [_content_key(*tracked_id.split(":")) for tracked_id in tracked_ids]
    values = await bot.redis_pool.mget(keys)

    contents: Dict[str, str] = {}
    for tracked_id, value in zip(tracked_ids, values):
        if value is None:
            continue

        try:
            contents[tracked_id] = fernet.decrypt(value).decode()
        except InvalidToken:
            log.warning("Failed to decrypt cached AutoMod message content for %s", tracked_id)

    return contents


async def delete_message_contents(bot: LightningBot, tracked_ids: Iterable[str]) -> None:
    """Deletes cached message content for the given tracked message ids.

    This is done as a defense-in-depth measure on top of the TTL, to minimize how long
    message content stays in the cache once it's no longer needed."""
    tracked_ids = list(tracked_ids)
    if not tracked_ids:
        return

    keys = [_content_key(*tracked_id.split(":")) for tracked_id in tracked_ids]
    await bot.redis_pool.delete(*keys)
