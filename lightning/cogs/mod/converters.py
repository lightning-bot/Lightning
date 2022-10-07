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
import re

import discord
from discord.ext import commands

from lightning import GuildContext


class BannedMember(commands.IDConverter):
    async def convert(self, ctx: GuildContext, argument: str) -> discord.BanEntry:
        if match := self._get_id_match(argument) or re.match(r'<@!?([0-9]{15,20})>$', argument):
            try:
                return await ctx.guild.fetch_ban(discord.Object(match.group(1)))
            except discord.NotFound as e:
                raise commands.BadArgument("This member has not been banned before.") from e

        ban_list = [en async for en in ctx.guild.bans()]
        entity = discord.utils.find(lambda u: str(u.user) == argument, ban_list)

        if entity is None:
            raise commands.BadArgument("This member has not been banned before.")
        return entity
