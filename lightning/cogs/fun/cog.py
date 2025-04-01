"""
Lightning.py - A Discord bot
Copyright (C) 2019-2025 LightSage

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

import datetime
import math
import random
from typing import Dict, Literal

import discord
from discord.ext import commands, tasks

from lightning import GuildContext, LightningBot, LightningCog, command

# Seasonal Changes: default=base warmth high=higher default temp low=a lower temp
SEASONAL_CHANGES = {"summer": {"default": 85, "high": 100, "low": 65},
                    "fall": {"default": 60, "high": 70, "low": 40},
                    "winter": {"default": 35, "high": 55, "low": 1},
                    "spring": {"default": 50, "high": 79, "low": 38}}

DEFAULT_CHANGE = {"default": 60, "high": 120, "low": 1}


# According to Meterological Data
# At some point, I'll make this change temperatures based on the month and not just seasons
def get_season() -> Dict[str, int]:
    now = datetime.datetime.now()
    if datetime.date(now.year, 6, 1) <= now.date() <= datetime.date(now.year, 8, 31):
        return SEASONAL_CHANGES["summer"]
    elif datetime.date(now.year, 9, 1) <= now.date() <= datetime.date(now.year, 11, 30):
        return SEASONAL_CHANGES["fall"]
    elif datetime.date(now.year, 12, 1) <= now.date() <= datetime.date(now.year, 2, 28):
        return SEASONAL_CHANGES["winter"]
    elif datetime.date(now.year, 3, 1) <= now.date() <= datetime.date(now.year, 5, 31):
        return SEASONAL_CHANGES["spring"]

    return DEFAULT_CHANGE


def fahrenheit_to_celsius(fahrenheit: int):
    return math.floor((fahrenheit - 32) * 5 / 9)


class Fun(LightningCog):
    """
    Commands to bring some engagement to your server
    """
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self.temp_type = "normal"
        self.switch_between_highs_and_lows.start()

    async def cog_unload(self) -> None:
        self.switch_between_highs_and_lows.stop()

    @tasks.loop(hours=1)
    async def switch_between_highs_and_lows(self):
        self.temp_type = random.choices(["normal", "high", "low"])[0]

    async def get_temperature(self, user_id: int):
        temp = await self.bot.redis_pool.get(f"lightning:fun:temperature:{user_id}")
        if not temp:
            temp = get_season().get(self.temp_type)
        return int(temp)

    def get_current_temp(self) -> int:
        return get_season().get(self.temp_type)

    def temperature_check(self, num: int, key: Literal["high", "low"]) -> bool:
        temp = get_season().get(key, 60) * 1.2
        return num > temp

    async def set_user_temperature(self, user_id: int, value: int):
        await self.bot.redis_pool.set(f"lightning:fun:temperature:{user_id}", str(value), ex=86400)  # 1 day expiration

    @command(hidden=True)
    @commands.cooldown(3, 60.0, commands.BucketType.user)
    async def warm(self, ctx: GuildContext, member: discord.Member):
        """Warms a member"""
        temp = await self.get_temperature(member.id) + random.randint(1, 10)
        check = self.temperature_check(temp, "high")
        if check is True:
            await ctx.send(f"You need to cool {member.mention} down!", ephemeral=True)
            return

        await self.set_user_temperature(member.id, temp)

        await ctx.send(f"{ctx.author.mention} warmed {member.mention}. "
                       f"{member.mention} is now {temp}°F. ({fahrenheit_to_celsius(temp)}°C)")

    @command(aliases=['chill'], hidden=True)
    @commands.cooldown(3, 60.0, commands.BucketType.user)
    async def cool(self, ctx: GuildContext, member: discord.Member):
        """Cools down a member"""
        temp = await self.get_temperature(member.id) - random.randint(1, 10)
        check = self.temperature_check(temp, "low")
        if check is False:
            await ctx.send(f"You need to warm {member.mention} up!", ephemeral=True)
            return

        await self.set_user_temperature(member.id, temp)

        await ctx.send(f"{ctx.author.mention} cooled {member.mention}. "
                       f"{member.mention} is now {temp}°F. ({fahrenheit_to_celsius(temp)}°C)")
