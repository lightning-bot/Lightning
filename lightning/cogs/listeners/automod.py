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

import datetime
import re
from typing import (TYPE_CHECKING, Any, Callable, Dict, List, Optional,
                    TypedDict, Union)

import aioredis
import discord
from discord.ext.commands.cooldowns import BucketType
from sanctum.exceptions import NotFound

from lightning import (AutoModCooldown, CommandLevel, LightningBot,
                       LightningCog, cache)
from lightning.constants import (AUTOMOD_EVENT_NAMES_MAPPING,
                                 COMMON_HOIST_CHARACTERS)
from lightning.models import GuildAutoModRulePunishment, PartialGuild
from lightning.utils import modlogformats

if TYPE_CHECKING:
    from lightning.cogs.mod import Moderation
    from lightning.cogs.reminders.cog import Reminders

    class AutoModGuildConfig(TypedDict):
        guild_id: int
        default_ignores: List[int]

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

    class AutoModMessage(discord.Message):
        guild: discord.Guild
        author: discord.Member


INVITE_REGEX = re.compile(r"(?:https?://)?discord(?:app)?\.(?:com/invite|gg)/[a-zA-Z0-9]+/?")
URL_REGEX = re.compile(r"https?:\/\/.*?$")


def invite_check(message):
    match = INVITE_REGEX.findall(message.content)
    return bool(match)


def url_check(message):
    match = URL_REGEX.findall(message.content)
    return bool(match)


class AutomodConfig:
    def __init__(self, bot: LightningBot, config: AutoModGuildConfig, rules: Dict[str, Any]) -> None:
        self.guild_id = config["guild_id"]
        self.default_ignores: List[int] = config.get("default_ignores", [])

        self.bot = bot

        self.message_spam: Optional[SpamConfig] = None
        self.mass_mentions: Optional[SpamConfig] = None
        self.message_content_spam: Optional[SpamConfig] = None
        self.invite_spam: Optional[SpamConfig] = None
        self.url_spam: Optional[SpamConfig] = None
        # "Features"
        self.auto_dehoist: Optional[BasicFeature] = None

        self.load_rules(rules)

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
                self.auto_dehoist = BasicFeature(rule)

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
    def from_model(cls, record: AutoModRulePayload, bucket_type: Union[BucketType, Callable], config: AutomodConfig,
                   *, check=None):
        return cls(record['count'], record['seconds'], record["punishment"], bucket_type,
                   f"automod:{record['type']}:{config.guild_id}", config.bot.redis_pool, check=check)

    async def update_bucket(self, message: discord.Message, increment: int = 1) -> bool:
        if self.check and self.check(message) is False:
            return False

        ratelimited = await self.cooldown.hit(message, incr_amount=increment)

        return bool(ratelimited)

    async def reset_bucket(self, message: discord.Message) -> None:
        # I wouldn't think there's a need for this but if you're using warn (for example), it'll double warn
        await self.cooldown.redis.delete(self.cooldown._key_maker(message))


class AutoMod(LightningCog, required=["Moderation"]):
    """Auto-moderation"""

    @cache.cached('guild_automod', cache.Strategy.raw)
    async def get_automod_config(self, guild_id: int):
        try:
            config = await self.bot.api.get_guild_automod_config(guild_id)
            rules = await self.bot.api.get_guild_automod_rules(guild_id)
        except NotFound:
            rules = None

            if not rules:
                return

            config = {"guild_id": guild_id}

        return AutomodConfig(self.bot, config, rules) if rules else None

    async def add_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> str:
        return await self.bot.get_cog("Moderation").add_punishment_role(guild_id, user_id, role_id,
                                                                        connection=connection)

    async def remove_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> None:
        return await self.bot.get_cog("Moderation").remove_punishment_role(guild_id, user_id, role_id,
                                                                           connection=connection)

    async def log_manual_action(self, guild: discord.Guild, target, moderator,
                                action: Union[modlogformats.ActionType, str], *, timestamp=None,
                                reason: Optional[str] = None, **kwargs) -> None:
        # We need this for bulk actions
        c: Moderation = self.bot.get_cog("Moderation")  # type: ignore
        return await c.log_manual_action(guild, target, moderator, action, timestamp=timestamp, reason=reason, **kwargs)

    async def is_member_whitelisted(self, message: discord.Message) -> bool:
        """Check that tells whether a member is exempt from automod or not"""
        # TODO: Check against a generic set of moderator permissions.
        record = await self.bot.get_guild_bot_config(message.guild.id)
        if not record or record.permissions is None:
            return False

        if record.permissions.levels is None:
            level = CommandLevel.User
        else:
            roles = message.author._roles if hasattr(message.author, "_roles") else []
            level = record.permissions.levels.get_user_level(message.author.id, roles)

        if level == CommandLevel.Blocked:  # Blocked to commands, not ignored by automod
            return False

        return level.value >= CommandLevel.Trusted.value

    # These only require one param, "message", because it contains all the information we want.
    async def _warn_punishment(self, message: AutoModMessage, *, reason):
        await self.log_manual_action(message.guild, message.author, self.bot.user, "WARN", reason=reason)

    async def _kick_punishment(self, message: AutoModMessage, *, reason):
        await message.author.kick(reason=reason)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "KICK",
                                     reason="Member triggered AutoMod")

    async def _time_ban_member(self, message: AutoModMessage, seconds: int, *, reason):
        duration = message.created_at + datetime.timedelta(seconds=seconds)
        cog: Reminders = self.bot.get_cog("Reminders")  # type: ignore
        timer_id = await cog.add_timer("timeban", message.created_at, duration, guild_id=message.guild.id,
                                       user_id=message.author.id, mod_id=self.bot.user.id, force_insert=True)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "TIMEBAN", expiry=duration,
                                     timer_id=timer_id, reason=reason)

    async def _ban_punishment(self, message: AutoModMessage, duration=None, *, reason):
        await message.author.ban(reason=reason)
        if duration:
            await self._time_ban_member(message, duration, reason=reason)
            return
        await self.log_manual_action(message.guild, message.author, self.bot.user, "BAN", reason=reason)

    async def _delete_punishment(self, message: discord.Message, **kwargs):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    async def get_mute_role(self, guild_id: int):
        cog: Moderation = self.bot.get_cog("Moderation")  # type: ignore
        cfg = await cog.get_mod_config(guild_id)
        if not cfg:
            # No mute role... Perhaps a bot log channel would be helpful to guilds...
            return

        guild = self.bot.get_guild(guild_id)
        if not cfg.mute_role_id:
            return

        return guild.get_role(cfg.mute_role_id)

    def can_timeout(self, message: AutoModMessage, duration: datetime.datetime):
        """Determines whether the bot can timeout a member.

        Parameters
        ----------
        message : AutoModMessage
            The message
        duration : datetime.datetime
            An instance of datetime.datetime

        Returns
        -------
        bool
            Returns True if the bot can timeout a member
        """
        me = message.guild.me
        if message.channel.permissions_for(me).moderate_members and \
                duration <= (message.created_at + datetime.timedelta(days=28)):
            return True
        return False

    async def _temp_mute_user(self, message: AutoModMessage, seconds: int, *, reason: str):
        duration = message.created_at + datetime.timedelta(seconds=seconds)

        if self.can_timeout(message, duration):
            await message.author.edit(timed_out_until=duration, reason=reason)
            return

        role = await self.get_mute_role(message.guild.id)
        if not role:
            # Report something went wrong...
            return

        if not message.channel.permissions_for(message.guild.me).manage_roles:
            return

        cog: Reminders = self.bot.get_cog('Reminders')  # type: ignore
        job_id = await cog.add_timer("timemute", message.created_at, duration,
                                     guild_id=message.guild.id, user_id=message.author.id, role_id=role.id,
                                     mod_id=self.bot.user.id, force_insert=True)
        await message.author.add_roles(role, reason=reason)

        await self.add_punishment_role(message.guild.id, message.author.id, role.id)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "TIMEMUTE",
                                     reason="Member triggered automod", expiry=duration, timer_id=job_id,
                                     timestamp=message.created_at)

    async def _mute_punishment(self, message: AutoModMessage, duration=None, *, reason: str):
        if duration:
            return await self._temp_mute_user(message, duration, reason=reason)

        if not message.channel.permissions_for(message.guild.me).manage_roles:
            return

        role = await self.get_mute_role(message.guild.id)
        if not role:
            return

        await message.author.add_roles(role, reason=reason)
        await self.add_punishment_role(message.guild.id, message.author.id, role.id)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "MUTE",
                                     reason="Member triggered automod", timestamp=message.created_at)

    punishments = {"WARN": _warn_punishment,
                   "KICK": _kick_punishment,
                   "BAN": _ban_punishment,
                   "DELETE": _delete_punishment,
                   "MUTE": _mute_punishment
                   }

    async def _handle_punishment(self, options: GuildAutoModRulePunishment, message: discord.Message,
                                 automod_rule_name: str):
        automod_rule_name = AUTOMOD_EVENT_NAMES_MAPPING.get(automod_rule_name.replace('_', '-'), "AutoMod rule")
        reason = f"{automod_rule_name} triggered"

        meth = self.punishments[str(options.type)]

        if options.type not in ("MUTE", "BAN"):
            await meth(self, message, reason=reason)
            return

        await meth(self, message, options.duration, reason=reason)

    async def check_message(self, message: discord.Message, config: AutomodConfig):
        async def handle_bucket(attr_name: str, increment: Optional[Callable[[discord.Message], int]] = None):
            obj: Optional[SpamConfig] = getattr(config, attr_name, None)
            if not obj:
                return

            # We would handle rule specific ignores here but that's not applicable at this time.

            if increment:
                rl = await obj.update_bucket(message, increment(message))
            else:
                rl = await obj.update_bucket(message)

            if rl is True:
                await obj.reset_bucket(message)
                await self._handle_punishment(obj.punishment, message, attr_name)

        await handle_bucket('mass_mentions', lambda m: len(m.mentions) + len(m.role_mentions))
        await handle_bucket('message_spam')
        await handle_bucket('message_content_spam')
        await handle_bucket('invite_spam')
        await handle_bucket('url_spam')

    @LightningCog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:  # DM Channels are exempt.
            return

        # Ignore system content
        if message.is_system():
            return

        # Ignore bots (for now)
        if message.author.bot:
            return

        # Ignore higher ups
        if hasattr(message.author, 'top_role') and message.guild.me.top_role < message.author.top_role:
            return

        check = await self.is_member_whitelisted(message)
        if check is True:
            return

        record = await self.get_automod_config(message.guild.id)
        if not record:
            return

        if record.is_ignored(message):
            return

        await self.check_message(message, record)

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild: Union[PartialGuild, discord.Guild]) -> None:
        await self.get_automod_config.invalidate(guild.id)

    @LightningCog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.name == after.name:
            return

        record = await self.get_automod_config(after.guild.id)
        if not record:
            return

        if not record.auto_dehoist:
            return

        cog: Moderation = self.bot.get_cog("Moderation")  # type: ignore
        await cog.dehoist_member(after, self.bot.user, COMMON_HOIST_CHARACTERS)

    # Remove ids from config
    @LightningCog.listener('on_member_remove')
    @LightningCog.listener('on_guild_channel_delete')
    @LightningCog.listener('on_guild_role_delete')
    async def on_snowflake_removal(self, payload):
        # payload: Union[discord.Member, discord.Role, discord.abc.GuildChannel]
        config = await self.get_automod_config(payload.guild.id)
        if not config:
            return

        try:
            config.default_ignores.remove(payload.id)
        except ValueError:
            return

        await self.bot.api.bulk_upsert_guild_automod_default_ignores(payload.guild.id, config.default_ignores)


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(AutoMod(bot))
