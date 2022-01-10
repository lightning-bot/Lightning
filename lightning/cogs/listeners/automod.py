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


class AutomodConfig:
    def __init__(self, record) -> None:
        records = read_file(toml_loads(record))
        self.message_spam: Optional[MessageConfigBase] = None
        self.mass_mentions: Optional[BaseTableModel] = None
        self.message_content_spam: Optional[MessageConfigBase] = None
        for record in records:
            if record.type == "mass-mentions":
                self.mass_mentions = record
            if record.type == "message-spam":
                self.message_spam = MessageConfigBase.from_model(record, BucketType.member)
            if record.type == "message-content-spam":
                self.message_content_spam = MessageConfigBase.from_model(record,
                                                                         lambda m: (m.author.id, len(m.content)))


class MessageConfigBase:
    """A class to make interacting with a message spam config easier..."""
    def __init__(self, rate, seconds, punishment_config, bucket_type, *, check=None) -> None:
        self.cooldown_bucket = CooldownMapping(Cooldown(rate, seconds), bucket_type)
        self.punishment: AutomodPunishmentModel = punishment_config

        if check and not callable(check):
            raise Exception("check must be a callable")

        self.check = check

    @classmethod
    def from_model(cls, record: MessageSpamModel, bucket_type):
        return cls(record.count, record.seconds, record.punishment, bucket_type)

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

    async def _ban_punishment(self, message: discord.Message):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        await message.author.ban(reason=reason)
        await self.log_manual_action(message.guild, message.author, self.bot.user, "BAN", reason=reason)

    async def _delete_punishment(self, message: discord.Message):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    punishments = {AutomodPunishmentEnum.WARN: _warn_punishment,
                   AutomodPunishmentEnum.KICK: _kick_punishment,
                   AutomodPunishmentEnum.BAN: _ban_punishment,
                   AutomodPunishmentEnum.DELETE: _delete_punishment
                   # PunishmentType.MUTE: self._mute_punishment
                   }

    @LightningCog.listener()
    async def on_message(self, message):
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
            meth = self.punishments[record.mass_mentions.punishment.type]
            await meth(self, message)

        if record.message_spam and record.message_spam.update_bucket(message) is True:
            record.message_spam.reset_bucket(message)  # Reset our bucket
            meth = self.punishments[record.message_spam.punishment.type]
            await meth(self, message)

        if record.message_content_spam and record.message_content_spam.update_bucket(message) is True:
            record.message_content_spam.reset_bucket(message)  # Reset our bucket
            meth = self.punishments[record.message_content_spam.punishment.type]
            await meth(self, message)

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild: Union[PartialGuild, discord.Guild]) -> None:
        await self.get_automod_config.invalidate(guild.id)


def setup(bot) -> None:
    bot.add_cog(AutoMod(bot))
