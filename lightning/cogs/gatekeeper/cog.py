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

from typing import Optional

import discord
from discord import app_commands

from lightning import GroupCog, GuildContext, group
from lightning.cache import Strategy, cached
from lightning.cogs.gatekeeper.models import GateKeeperConfig


class Gatekeeper(GroupCog):
    """Commands to manage gatekeeper"""

    @GroupCog.listener()
    async def on_member_join(self, member: discord.Member):
        gatekeeper = await self.get_gatekeeper_config(member.guild.id)
        if not gatekeeper:
            return

        if not gatekeeper.active:
            return

        await gatekeeper.gatekeep_member(member)

    @cached("gatekeeper_config", Strategy.raw)
    async def get_gatekeeper_config(self, guild_id: int) -> Optional[GateKeeperConfig]:
        ...

    @group(aliases=['joingate'])
    @app_commands.guild_only()
    async def gatekeeper(self, ctx: GuildContext):
        ...
