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
from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Callable, List, Optional, TypedDict, Union

import discord
import redis.asyncio as aioredis
from discord.ext.commands import BucketType

from lightning import AutoModCooldown, LightningBot
from lightning.models import GuildAutoModRulePunishment

if TYPE_CHECKING:
    class AutoModGuildConfig(TypedDict):
        guild_id: int
        default_ignores: List[int]
        warn_threshold: Optional[int]
        warn_punishment: Optional[str]
        rules: List[AutoModRulePayload]

    class AutoModRulePunishmentPayload(TypedDict):
        type: str
        duration: Optional[str]

    class AutoModRulePayload(TypedDict):
        guild_id: int
        type: str
        count: int
        seconds: int
        ignores: List[int]
        punishment: AutoModRulePunishmentPayload


INVITE_REGEX = re.compile(r"(?:https?://)?discord(?:app)?\.(?:com/invite|gg)/[a-zA-Z0-9]+/?")
URL_REGEX = re.compile(r"https?:\/\/.*?$")


def invite_check(message: discord.Message):
    match = INVITE_REGEX.findall(message.content)
    return bool(match)


def url_check(message):
    match = URL_REGEX.findall(message.content)
    return bool(match)


class AutomodConfig:
    def __init__(self, bot: LightningBot, config: AutoModGuildConfig) -> None:
        self.guild_id: int = config["guild_id"]
        self.default_ignores: set[int] = set(config.get("default_ignores", []))
        self.warn_threshold = config.get('warn_threshold')
        self.warn_punishment = config.get('warn_punishment')

        self.bot = bot

        self.message_spam: Optional[SpamConfig] = None
        self.mass_mentions: Optional[SpamConfig] = None
        self.message_content_spam: Optional[SpamConfig] = None
        self.invite_spam: Optional[SpamConfig] = None
        self.url_spam: Optional[SpamConfig] = None
        # "Basic Features"
        self.auto_dehoist: bool = False
        self.auto_normalize: bool = False

        self.load_rules(config['rules'])

    def load_rules(self, rules):
        for rule in rules:
            if rule['type'] == "mass-mentions":
                self.mass_mentions = SpamConfig.from_model(rule, BucketType.member, self)
            if rule['type'] == "message-spam":
                self.message_spam = SpamConfig.from_model(rule, BucketType.member, self)
            if rule['type'] == "message-content-spam":
                self.message_content_spam = SpamConfig.from_model(rule,
                                                                  lambda m: (m.author.id, len(m.content)), self)
            if rule['type'] == "invite-spam":
                self.invite_spam = SpamConfig.from_model(rule, BucketType.member, self, check=invite_check)
            if rule['type'] == "url-spam":
                self.url_spam = SpamConfig.from_model(rule, BucketType.member, self, check=url_check)
            if rule['type'] == "auto-dehoist":
                self.auto_dehoist = True
            if rule['type'] == "auto-normalize":
                self.auto_normalize = True

    def is_ignored(self, message: discord.Message):
        if not self.default_ignores:
            return False

        return any(a in self.default_ignores for a in getattr(message.author, '_roles', [])) or message.author.id in self.default_ignores or message.channel.id in self.default_ignores  # noqa


class BasicFeature:
    __slots__ = ("punishment")

    def __init__(self, data) -> None:
        self.punishment = GuildAutoModRulePunishment(data['punishment'])


class SpamConfig:
    __slots__ = ("cooldown", "punishment", "check")

    """A class to make interacting with a message spam config easier..."""
    def __init__(self, rate: int, seconds: int, punishment_config: AutoModRulePunishmentPayload,
                 bucket_type: Union[BucketType, Callable[[discord.Message], str]], key: str,
                 redis_pool: aioredis.Redis, *,
                 check: Optional[Callable[[discord.Message], bool]] = None) -> None:
        self.cooldown = AutoModCooldown(key, rate, seconds, redis_pool, bucket_type)
        self.punishment = GuildAutoModRulePunishment(punishment_config)

        if check and not callable(check):
            raise TypeError("check must be a callable")

        self.check = check

    @classmethod
    def from_model(cls, record: AutoModRulePayload, bucket_type: Union[BucketType, Callable[[discord.Message], str]],
                   config: AutomodConfig, *, check=None):
        return cls(record['count'], record['seconds'], record["punishment"], bucket_type,
                   f"automod:{record['type']}:{config.guild_id}", config.bot.redis_pool, check=check)

    async def update_bucket(self, message: discord.Message, increment: int = 1) -> bool:
        if self.check and self.check(message) is False:
            return False

        ratelimited = await self.cooldown.hit(message, incr_amount=increment)
        # Track message IDs to delete
        await self.cooldown.redis.sadd(f"{self.cooldown._key_maker(message)}:messages",
                                       f"{message.channel.id}:{message.id}")

        return bool(ratelimited)

    async def fetch_responsible_messages(self, message: discord.Message):
        """Gets the message IDs that triggered this AutoMod rule"""
        return await self.cooldown.redis.smembers(f"{self.cooldown._key_maker(message)}:messages")

    async def reset_bucket(self, message: discord.Message) -> None:
        # I wouldn't think there's a need for this but if you're using warn (for example), it'll double warn
        await self.cooldown.redis.delete(self.cooldown._key_maker(message),
                                         f"{self.cooldown._key_maker(message)}:messages")


class GateKeeperConfig:
    def __init__(self, bot, record, members) -> None:
        self.bot: LightningBot = bot
        self.guild_id: int = record['guild_id']
        self.active = record['active']
        self.active_since = None
        self.role_id: Optional[int] = record['role_id']
        self.verification_channel_id: Optional[int] = record['verification_channel_id']
        self.members: set[int] = {r['member_id'] for r in members if r['pending_automod_action'] is None}
        self.gtkp_loop = asyncio.create_task(self._loop())

    @property
    def role(self) -> discord.Role:
        guild = self.bot.get_guild(self.guild_id)  # should never be None
        return guild.get_role(self.role_id)  # type: ignore

    async def _loop(self):
        # for quick ref, result is a list of [key, value]
        while self.active:
            result: List[str] = await self.bot.redis_pool.brpop([f"lightning:automod:gatekeeper:{self.guild_id}:add",
                                                                f"lightning:automod:gatekeeper:{self.guild_id}:remove"],
                                                                0)  # type: ignore
            member_id = int(result[1])
            state = result[0].split(":")[-1]

            if state == "remove":
                role_method = self.bot.http.remove_role
            else:
                role_method = self.bot.http.add_role

            try:
                if state == "add":
                    await role_method(self.guild_id, member_id, self.role_id,
                                      reason='Gatekeeper currently active')
                elif state == "remove":
                    await role_method(self.guild_id, member_id, self.role_id,
                                      reason='Completed Gatekeeper verification')
                    await self.bot.pool.execute("DELETE FROM pending_gatekeeper_members WHERE guild_id=$1 AND "
                                                "member_id=$2;",
                                                self.guild_id, member_id)
            except discord.DiscordServerError:
                await self.bot.redis_pool.lpush(result[0], member_id)
            except discord.HTTPException:
                pass

    async def gatekeep_member(self, member: discord.Member):
        query = """INSERT INTO pending_gatekeeper_members (guild_id, member_id)
                   VALUES ($1, $2)
                   ON CONFLICT DO NOTHING;"""
        await self.bot.pool.execute(query, member.guild.id, member.id)
        self.members.add(member.id)
        await self.bot.redis_pool.lpush(f"lightning:automod:gatekeeper:{member.guild.id}:add", member.id)

    async def remove_member(self, member: discord.Member):
        """Queues a member to be removed from verification (i.e. they verified themselves)"""
        await self.bot.redis_pool.lpush(f"lightning:automod:gatekeeper:{member.guild.id}:remove", member.id)
        self.members.remove(member.id)

    async def disable(self):
        self.active = False
        # Moves the members from the add list to the removal list
        members = await self.bot.redis_pool.lrange(f"lightning:automod:gatekeeper:{self.guild_id}:add", 0, -1)
        await self.bot.redis_pool.lpush(f"lightning:automod:gatekeeper:{self.guild_id}:remove", *members)
        self.members.clear()
