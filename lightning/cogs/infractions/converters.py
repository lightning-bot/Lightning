"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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

from typing import Any, Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands
from sanctum.exceptions import NotFound

from lightning import GuildContext, LightningBot
from lightning.enums import ActionType
from lightning.models import InfractionRecord


class InfractionFilterFlags(commands.FlagConverter):
    member: discord.Member
    active: bool = commands.flag(default=True)
    moderator: Optional[discord.Member]
    type: Optional[Literal['WARN', 'KICK', 'BAN', 'TEMPBAN', 'TEMPMUTE', 'MUTE']]


class InfractionTypeConverter(commands.Converter):
    async def convert(self, ctx: GuildContext, argument: str):
        argument = argument.upper().strip()
        try:
            action = ActionType[argument]
        except KeyError:
            raise commands.BadArgument(f"Unable to convert \"{argument}\".")

        return action.value


class InfractionConverter(commands.Converter, app_commands.Transformer):
    @property
    def type(self):
        return discord.AppCommandOptionType.integer

    async def transform(self, interaction: discord.Interaction[LightningBot], value: Any) -> InfractionRecord:
        try:
            record = await interaction.client.api.get_infraction(interaction.guild.id, value)
        except NotFound:
            raise commands.UserInputError(f"An infraction with ID {value} was not found!")

        return InfractionRecord(interaction.client, record)

    async def convert(self, ctx: GuildContext, argument: str) -> InfractionRecord:
        try:
            num = int(argument)
        except ValueError:
            raise commands.BadArgument(f"Converting to \"int\" failed for parameter \"{ctx.current_parameter}\"")

        try:
            record = await ctx.bot.api.get_infraction(ctx.guild.id, num)
        except NotFound:
            raise commands.UserInputError(f"An infraction with ID {num} was not found!")

        return InfractionRecord(ctx.bot, record)
