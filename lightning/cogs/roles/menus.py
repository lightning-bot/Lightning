from typing import List

import asyncpg
import discord
from discord.ext import menus

from lightning.utils.paginator import Paginator


class RoleSource(menus.ListPageSource):
    async def format_page(self, menu: Paginator, entries: List[discord.Role]):
        embed = discord.Embed(title="Self-Assignable Roles", color=discord.Color.greyple())
        embed.description = '\n'.join([f"{role.mention} (ID: {role.id})" for role in entries])
        return embed


class PersistedRolesSource(menus.ListPageSource):
    async def format_page(self, menu: Paginator, records: List[asyncpg.Record]):
        embed = discord.Embed(title="Persisted Roles", color=discord.Color.greyple())
        tmp = []
        for record in records:
            roles = [f"╙ <@&{role}> (ID: {role})\n" for role in record['punishment_roles']]
            # Discord really don't like ZWS in embeds apparently
            tmp.append(f"<@{record['user_id']}> ({record['user_id']}):\n{''.join(roles)}\n")
        embed.description = ''.join(tmp)
        return embed
