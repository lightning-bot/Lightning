"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

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

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from lightning.errors import LightningCommandError
from lightning.utils.time import FutureTime, ShortTime

if TYPE_CHECKING:
    from lightning import LightningBot, LightningContext
    from lightning.cogs.reminders.cog import Reminders


class TimeZoneConverter(commands.Converter):
    async def convert(self, ctx: LightningContext, argument: str):
        try:
            return ZoneInfo(argument)
        except Exception:
            raise commands.UserInputError("I couldn't find that timezone!")


class TimeParseTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[LightningBot], argument: str) -> datetime:
        cog: Optional[Reminders] = itx.client.get_cog("Reminders")  # type: ignore
        if not cog:
            raise LightningCommandError("Reminders cog is not loaded!")

        tz = await cog.get_user_tzinfo(itx.user.id)

        try:
            return ShortTime(argument, now=itx.created_at, tz=tz).dt
        except Exception:
            try:
                return FutureTime(argument, now=itx.created_at, tz=tz).dt
            except Exception:
                raise LightningCommandError("I couldn't parse that time!")
