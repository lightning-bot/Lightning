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
import discord

from lightning import LightningBot


class GateKeeperConfig:
    def __init__(self, bot, record) -> None:
        self.bot: LightningBot = bot
        self.guild_id = record['guild_id']
        self.active = record['active']
        self.role_id = record['role_id']

    @property
    def role(self) -> discord.Role:
        guild = self.bot.get_guild(self.guild_id)  # should never be None
        return guild.get_role(self.role_id)  # type: ignore

    async def gatekeep_member(self, member: discord.Member):
        await member.add_roles(self.role, reason="Gatekeeper active")
