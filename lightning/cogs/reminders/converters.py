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

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from discord.ext import commands

if TYPE_CHECKING:
    from lightning import LightningContext


class TimeZoneConverter(commands.Converter):
    async def convert(self, ctx: LightningContext, argument: str):
        try:
            return ZoneInfo(argument)
        except Exception:
            raise commands.UserInputError("I couldn't find that timezone!")
