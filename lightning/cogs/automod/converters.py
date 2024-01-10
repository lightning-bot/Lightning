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
from dataclasses import dataclass
from typing import Union

import discord
from discord.ext import commands

from lightning import GuildContext
from lightning.constants import AUTOMOD_COMMAND_CONFIG_REGEX


@dataclass
class AutoModDurationResponse:
    count: int
    seconds: int


class AutoModDuration(commands.Converter):
    async def convert(self, ctx: GuildContext, argument: str) -> AutoModDurationResponse:
        if match := AUTOMOD_COMMAND_CONFIG_REGEX.match(argument):
            return AutoModDurationResponse(int(match['count']), int(match['seconds']))

        # We attempt to parse the rest...
        args = argument.split()
        if len(args) > 2 or len(args) < 2:
            raise commands.UserInputError(
                "I couldn't figure out what you wanted. See `help automod rules add` for more information.")

        try:
            count = int(args[0])
            seconds = int(args[1])
        except ValueError as e:
            raise commands.UserInputError(
                "I couldn't figure out what you wanted. See `help automod rules add` for more information.") \
                from e

        return AutoModDurationResponse(count, seconds)


IgnorableEntities = Union[discord.Role, discord.Member, discord.TextChannel, discord.Thread]
