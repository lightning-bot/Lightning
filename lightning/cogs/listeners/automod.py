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
import datetime
import re
from typing import Optional, Union

import discord
from discord.ext.commands.cooldowns import (BucketType, Cooldown,
                                            CooldownMapping)
from tomlkit import loads as toml_loads

from lightning import CommandLevel, LightningCog, cache
from lightning.models import PartialGuild
from lightning.utils import modlogformats
from lightning.utils.automod_parser import (AutomodPunishmentEnum,
                                            AutomodPunishmentModel,
                                            BaseTableModel, MessageSpamModel,
                                            read_file)
from lightning.utils.time import ShortTime

INVITE_REGEX = re.compile(r"(?:https?://)?discord(?:app)?\.(?:com/invite|gg)/[a-zA-Z0-9]+/?")
URL_REGEX = re.compile(r"https?:\/\/.*?$")


def invite_check(message):
    match = INVITE_REGEX.match(message.content)
    return bool(match)


def url_check(message):
    match = URL_REGEX.findall(message.content)
    return bool(match)


class AutomodConfig:
    def __init__(self, record) -> None:
        records = read_file(toml_loads(record))
        self.message_spam: Optional[MessageConfigBase] = None
        self.mass_mentions: Optional[BaseTableModel] = None
        self.message_content_spam: Optional[MessageConfigBase] = None
        self.invite_spam: Optional[MessageConfigBase] = None
        self.url_spam: Optional[MessageConfigBase] = None
        for record in records:
            if record.type == "mass-mentions":
                self.mass_mentions = record
            if record.type == "message-spam":
                self.message_spam = MessageConfigBase.from_model(record, BucketType.member)
            if record.type == "message-content-spam":
                self.message_content_spam = MessageConfigBase.from_model(record,
                                                                         lambda m: (m.author.id, len(m.content)))
            if record.type == "invite-spam":
                self.invite_spam = MessageConfigBase.from_model(record, BucketType.member, check=invite_check)
            if record.type == "url-spam":
                self.url_spam = MessageConfigBase.from_model(record, BucketType.member, check=url_check)


class MessageConfigBase:
    """A class to make interacting with a message spam config easier..."""
    def __init__(self, rate, seconds, punishment_config, bucket_type, *, check=None) -> None:
        self.cooldown_bucket = CooldownMapping(Cooldown(rate, seconds), bucket_type)
        self.punishment: AutomodPunishmentModel = punishment_config

        if check and not callable(check):
            raise Exception("check must be a callable")

        self.check = check

    @classmethod
    def from_model(cls, record: MessageSpamModel, bucket_type, *, check=None):
        return cls(record.count, record.seconds, record.punishment, bucket_type, check=check)

    def update_bucket(self, message: discord.Message) -> bool:
        if self.check and self.check(message) is False:
            return

        b = self.cooldown_bucket.get_bucket(message)
        ratelimited = b.update_rate_limit(message.created_at.timestamp())
        return bool(ratelimited)

    def reset_bucket(self, message: discord.Message) -> None:
        b = self.cooldown_bucket.get_bucket(message)
        b.reset()


class AutoMod(LightningCog, required=["Mod"]):
    """Auto-moderation"""

    @cache.cached('automod_config', cache.Strategy.raw)
    async def get_automod_config(self, guild_id: int):
        query = """SELECT config FROM automod WHERE guild_id=$1;"""
        record = await self.bot.pool.fetchval(query, guild_id)
        return AutomodConfig(record) if record else None

    async def add_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> str:
        return await self.bot.get_cog("Mod").add_punishment_role(guild_id, user_id, role_id, connection=connection)

    async def remove_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> None:
        return await self.bot.get_cog("Mod").remove_punishment_role(guild_id, user_id, role_id, connection=connection)

    async def log_manual_action(self, guild: discord.Guild, target, moderator,
                                action: Union[modlogformats.ActionType, str], *, timestamp=None,
                                reason: Optional[str] = None, **kwargs) -> None:
        # We need this for bulk actions
        c = self.bot.get_cog("Mod")
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
    async def _warn_punishment(self, message: discord.Message):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        await self.log_manual_action(message.guild, message.author, self.bot.user, "WARN", reason=reason)

    async def _kick_punishment(self, message: discord.Message):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        await message.author.kick(reason=reason)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "KICK",
                                     reason="Member triggered automod")

    async def _time_ban_member(self, message: discord.Message, duration: str):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        duration = ShortTime(duration, now=message.created_at)
        cog = self.bot.get_cog("Reminders")
        timer_id = await cog.add_job("timeban", message.created_at, duration.dt, guild_id=message.guild.id,
                                     user_id=message.author.id, mod_id=self.bot.user.id, force_insert=True)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "TIMEBAN", expiry=duration.dt,
                                     timer_id=timer_id, reason=reason)

    async def _ban_punishment(self, message: discord.Message, duration=None):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        await message.author.ban(reason=reason)
        if duration:
            await self._time_ban_member(message, duration)
            return
        await self.log_manual_action(message.guild, message.author, self.bot.user, "BAN", reason=reason)

    async def _delete_punishment(self, message: discord.Message):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    async def get_mute_role(self, guild_id: int, *, temp=False):
        cog = self.bot.get_cog("Mod")
        cfg = await cog.get_mod_config(guild_id)
        if not cfg:
            # No mute role... Perhaps a bot log channel would be helpful to guilds...
            return
        guild = self.bot.get_guild(guild_id)
        if not cfg.temp_mute_role_id and not cfg.mute_role_id:
            return

        role = guild.get_role(cfg.temp_mute_role_id) if temp is True else None
        if role is None:
            role = guild.get_role(cfg.mute_role_id)
        return role

    def can_timeout(self, message: discord.Message, duration: ShortTime):
        """Determines whether the bot can timeout a member.

        Parameters
        ----------
        message : discord.Message
            The message
        duration : ShortTime
            An instance of ShortTime

        Returns
        -------
        bool
            Returns True if the bot can timeout a member
        """
        me = message.guild.get_member(self.bot.user.id)
        if message.channel.permissions_for(me).moderate_members:
            if duration.dt <= (message.created_at + datetime.timedelta(days=29)):
                return True
        return False

    async def _temp_mute_user(self, message: discord.Message, duration):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        duration = ShortTime(duration, now=message.created_at)

        if self.can_timeout(message, duration):
            await message.author.edit(timed_out_until=duration.dt, reason=reason)
            return

        role = await self.get_mute_role(message.guild.id, temp=True)
        if not role:
            # Report something went wrong...
            return

        if not message.channel.permissions_for(message.guild.get_member(self.bot.user.id)).manage_roles:
            return

        cog = self.bot.get_cog('Reminders')
        job_id = await cog.add_job("timemute", message.created_at, duration.dt,
                                   guild_id=message.guild.id, user_id=message.author.id, role_id=role.id,
                                   mod_id=self.bot.user.id, force_insert=True)
        await message.author.add_roles(role, reason=reason)

        await self.add_punishment_role(message.guild.id, message.author.id, role.id)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "TIMEMUTE",
                                     reason="Member triggered automod", expiry=duration.dt, timer_id=job_id,
                                     timestamp=message.created_at)

    async def _mute_punishment(self, message: discord.Message, duration=None):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        if duration:
            return await self._temp_mute_user(message, duration)

        if not message.channel.permissions_for(message.guild.get_member(self.bot.user.id)).manage_roles:
            return

        role = await self.get_mute_role(message.guild.id)
        if not role:
            return

        await message.author.add_roles(role, reason=reason)
        await self.add_punishment_role(message.guild.id, message.author.id, role.id)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "MUTE",
                                     reason="Member triggered automod", timestamp=message.created_at)

    punishments = {AutomodPunishmentEnum.WARN: _warn_punishment,
                   AutomodPunishmentEnum.KICK: _kick_punishment,
                   AutomodPunishmentEnum.BAN: _ban_punishment,
                   AutomodPunishmentEnum.DELETE: _delete_punishment,
                   AutomodPunishmentEnum.MUTE: _mute_punishment
                   }

    async def _handle_punishment(self, options: AutomodPunishmentModel, message: discord.Message):
        meth = self.punishments[options.type]

        if options.type not in (AutomodPunishmentEnum.MUTE, AutomodPunishmentEnum.BAN):
            await meth(self, message)
            return

        await meth(self, message, options.duration)

    @LightningCog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:  # DM Channels are exempt.
            return

        # TODO: Ignored channels
        check = await self.is_member_whitelisted(message)
        if check is True:
            return

        record = await self.get_automod_config(message.guild.id)
        if not record:
            return

        if record.mass_mentions and len(message.mentions) >= record.mass_mentions.count:
            await self._handle_punishment(record.mass_mentions.punishment, message)

        if record.message_spam and record.message_spam.update_bucket(message) is True:
            record.message_spam.reset_bucket(message)  # Reset our bucket
            await self._handle_punishment(record.message_spam.punishment, message)

        if record.invite_spam and record.invite_spam.update_bucket(message) is True:
            record.invite_spam.reset_bucket(message)  # Reset our bucket
            await self._handle_punishment(record.invite_spam.punishment, message)

        if record.url_spam and record.url_spam.update_bucket(message) is True:
            record.url_spam.reset_bucket(message)  # Reset our bucket
            await self._handle_punishment(record.url_spam.punishment, message)

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild: Union[PartialGuild, discord.Guild]) -> None:
        await self.get_automod_config.invalidate(guild.id)


def setup(bot) -> None:
    bot.add_cog(AutoMod(bot))
