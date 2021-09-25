"""
Lightning.py - A Discord bot
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
import contextlib

import discord
from discord.ext.commands import Cooldown, CooldownMapping

from lightning import LightningBot, LightningCog

TWL_HACKING = 283769550611152897
MODERATION_LOGS = 689178510086111237


def content_bucket_key(message):
    # Additionally we'd check guild id but not needed for a one guild thing
    return (message.author.id, message.content)


class TWLSpam(LightningCog):
    def __init__(self, bot: LightningBot):
        self.bot = bot
        self.spam_bucket = CooldownMapping(Cooldown(9.0, 15.0), content_bucket_key)

    @LightningCog.listener()
    async def on_message(self, message):
        # Ignore DMs
        if not message.guild:
            return

        # Ignore any guild other than DSi Mode Hacking
        if message.guild.id != TWL_HACKING:
            return

        # Ignore bots
        if message.author.bot:
            return

        bucket = self.spam_bucket.get_bucket(message)
        ratelimited = bucket.update_rate_limit(message.created_at.timestamp())

        if not ratelimited:
            return

        try:
            await message.author.ban(reason="Auto-banned for message spam")
            with contextlib.suppress(discord.HTTPException):
                await message.channel.send(f"Auto banned {str(message.author)} | {message.author.id} "
                                           "for message content spam")
            cog = self.bot.get_cog("Mod")
            await cog.log_manual_action(message.guild, message.author, self.bot.user, "BAN",
                                        timestamp=message.created_at, reason="Auto-banned for message spam")
        except discord.HTTPException:
            ch = message.guild.get_channel(MODERATION_LOGS)
            if not ch:
                return
            await ch.send(f"Failed to auto ban {str(message.author)} | {message.author.id}")


def setup(bot: LightningBot) -> None:
    bot.add_cog(TWLSpam(bot))
