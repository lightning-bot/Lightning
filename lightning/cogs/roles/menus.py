from typing import List

import discord
from discord.ext import menus

from lightning.utils.paginator import Paginator


class RoleSource(menus.ListPageSource):
    async def format_page(self, menu: Paginator, entries: List[discord.Role]):
        embed = discord.Embed(title="Self-Assignable Roles", color=discord.Color.greyple())
        embed.description = '\n'.join([f"{role.mention} (ID: {role.id})" for role in entries])
        return embed
