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

from typing import TYPE_CHECKING

from .bot_meta import BotMeta
from .discord_meta import DiscordMeta
from .message import MessageInfo

if TYPE_CHECKING:
    from lightning import LightningBot


class Info(BotMeta, DiscordMeta, MessageInfo):
    """
    Commands with information about the bot or Discord
    """
    pass


def setup(bot: LightningBot):
    bot.add_cog(Info(bot))

    if bot.config['bot'].get("support_server_invite", None) is None:
        bot.remove_command("support")
