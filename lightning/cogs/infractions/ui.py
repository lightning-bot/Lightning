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
from datetime import datetime
from typing import Any, Optional, Union

import discord
from discord.ext import menus

from lightning import GuildContext
from lightning.enums import ActionType
from lightning.formatters import truncate_text
from lightning.models import InfractionRecord
from lightning.utils.modlogformats import base_user_format
from lightning.utils.paginator import Paginator
from lightning.utils.time import add_tzinfo


class InfractionPaginator(Paginator):
    def __init__(self, source: menus.PageSource, context: GuildContext, /, *, timeout: Optional[float] = 90):
        super().__init__(source, context=context, timeout=timeout)
        self.bot = context.bot


class InfractionSource(menus.ListPageSource):
    def __init__(self, entries, *, member: Optional[Union[discord.User, discord.Member]] = None):
        super().__init__(entries, per_page=5)
        self.member = member

    async def format_member_page(self, menu: InfractionPaginator, entries):
        embed = discord.Embed(color=discord.Color.dark_gray(), title=f"Infractions for {self.member}")
        for entry in entries:
            moderator = menu.bot.get_user(entry['moderator_id']) or entry['moderator_id']
            reason = entry['reason'] or 'No reason provided.'
            action = str(ActionType(entry['action'])).capitalize()
            dt = add_tzinfo(datetime.fromisoformat(entry['created_at']))
            embed.add_field(name=f"{entry['id']}: {action} at "
                            f"{discord.utils.format_dt(dt)}",
                            value=f"**Moderator**: {base_user_format(moderator)}\n"
                            f"**Reason**: {truncate_text(reason, 45)}", inline=False)
        return embed

    async def format_all_page(self, menu: InfractionPaginator, entries):
        embed = discord.Embed(color=discord.Color.dark_gray())
        for entry in entries:
            user = menu.bot.get_user(entry['user_id']) or entry['user_id']
            mod = menu.bot.get_user(entry['moderator_id']) or entry['moderator_id']
            reason = entry['reason'] or 'No reason provided.'
            action = str(ActionType(entry['action'])).capitalize()
            dt = add_tzinfo(datetime.fromisoformat(entry['created_at']))
            embed.add_field(name=f"{entry['id']}: {action} at "
                            f"{discord.utils.format_dt(dt)}",
                            value=f"**User**: {base_user_format(user)}\n**Moderator**: {base_user_format(mod)}"
                            f"\n**Reason**: {truncate_text(reason, 45)}",
                            inline=False)
        return embed

    async def format_page(self, menu: InfractionPaginator, entries):
        if self.member:
            return await self.format_member_page(menu, entries)
        else:
            return await self.format_all_page(menu, entries)


class SingularInfractionSource(menus.ListPageSource):
    def __init__(self, entries):
        super().__init__(entries, per_page=1)

    async def format_page(self, menu: InfractionPaginator, entry: dict[str, Any]):
        color = discord.Color.green() if entry['active'] else discord.Color.dark_gray()
        record = InfractionRecord(menu.bot, entry)
        embed = discord.Embed(color=color, title=str(record.action).capitalize(),
                              timestamp=add_tzinfo(record.created_at))
        embed.description = record.reason or "No reason provided"
        embed.set_footer(text="Infraction created at")
        return embed
