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
from __future__ import annotations

import math
import urllib.parse
from typing import TYPE_CHECKING

import discord
from discord.ext import menus

if TYPE_CHECKING:
    import aiohttp

    from lightning.cogs.api.models import CratesIOResponse


class CrateViewer(menus.KeysetPageSource):
    def __init__(self, search_term: str, *, session: aiohttp.ClientSession):
        self.session = session
        self.search_term = search_term

    def is_paginating(self) -> bool:
        return True

    async def request(self, query: str) -> dict:
        async with self.session.get(f"https://crates.io/api/v1/crates{query}") as resp:
            data = await resp.json()
        return data

    async def get_page(self, specifier) -> CratesIOResponse:
        query = f"?q={urllib.parse.quote(self.search_term)}"
        if specifier.reference is not None:
            if specifier.direction is menus.PageDirection.after:
                if specifier.reference.next_page is None:
                    raise ValueError
                query = specifier.reference.next_page
            else:
                if specifier.reference.previous_page is None:
                    raise ValueError
                query = specifier.reference.previous_page
        elif specifier.direction is menus.PageDirection.before:
            data = await self.request(query)
            query += f"&page={math.ceil(data['meta']['total'] / 10)}"

        data = await self.request(query)

        obj = CratesIOResponse(data)
        if not obj.crates:
            raise ValueError

        return obj

    async def format_page(self, menu, page) -> discord.Embed:
        v = "\n".join(f"**Exact Match** [{p.name}](https://crates.io/crates/{p.id})" if p.exact_match else
                      f"[{p.name}](https://crates.io/crates/{p.id})" for p in page.crates)
        embed = discord.Embed(title=f"Results for {self.search_term}", color=0x3B6837,
                              description=v)
        return embed
