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
import asyncio
from typing import Optional

import discord
from discord.ext import menus
from discord.ext.menus.views import ViewMenuPages

from lightning.ui import StopButton, UpdateableMenu


class Paginator(UpdateableMenu):
    def __init__(self, source: menus.PageSource, /, *, timeout: Optional[float] = 90):
        super().__init__(clear_view_after=True, timeout=timeout)
        self.source: menus.PageSource = source
        self.current_page: int = 0

        self.add_item(StopButton(label="Stop", style=discord.ButtonStyle.danger))

    @property
    def max_pages(self) -> int:
        return self.source.get_max_pages() - 1

    async def format_initial_message(self, ctx):
        await self.source._prepare_once()
        page = await self._get_page(self.current_page)
        return self._assume_message_kwargs(page)

    async def _get_page(self, num: int):
        page = await self.source.get_page(num)
        page = await self.source.format_page(self, page)
        return page

    async def show_page(self, interaction: discord.Interaction, page_number: int):
        self.current_page = page_number
        page = await self._get_page(self.current_page)
        kwargs = self._assume_message_kwargs(page)

        await self.update_components()

        if interaction.response.is_done():
            await self.message.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

    async def update_components(self) -> None:
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.max_pages
        # First & Last
        self.first_page_button.disabled = self.current_page == 0
        self.last_page_button.disabled = self.current_page >= self.max_pages

    async def start(self, ctx, *, wait: bool = True):
        if not self.source.is_paginating():
            # Does not require pagination
            page = await self._get_page(0)
            kwargs = self._assume_message_kwargs(page)
            await ctx.send(**kwargs)
            return

        await super().start(ctx, wait=wait)

    @discord.ui.button(label="<<")
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 0)

    @discord.ui.button(label="Previous")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, self.current_page - 1)

    @discord.ui.button(label="Next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, self.current_page + 1)

    @discord.ui.button(label=">>")
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, self.max_pages)


class BasicEmbedMenu(menus.ListPageSource):
    def __init__(self, data, *, per_page=4, embed=None):
        self.embed = embed
        super().__init__(data, per_page=per_page)

    async def format_page(self, menu, entries) -> discord.Embed:
        if self.embed:
            embed = self.embed
        else:
            embed = discord.Embed(color=discord.Color.greyple())
        embed.description = "\n".join(entries)
        embed.set_footer(text=f"Page {menu.current_page + 1} of {self.get_max_pages()}")
        return embed


class InfoMenuPages(ViewMenuPages):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @menus.button("\N{INFORMATION SOURCE}\ufe0f", position=menus.Last(3))
    async def info_page(self, payload) -> None:
        """shows you this message"""
        messages = ['Welcome to the interactive paginator!\n']
        messages.append('This interactively allows you to see pages of text by navigating with '
                        'reactions. They are as follows:\n')
        for emoji, button in self.buttons.items():
            messages.append(f'{str(emoji)} {button.action.__doc__}')

        embed = discord.Embed(color=discord.Color.blurple())
        embed.clear_fields()
        embed.description = '\n'.join(messages)
        embed.set_footer(text=f"We were on page {self.current_page + 1} before this message.")
        await self.message.edit(content=None, embed=embed)

        async def go_back_to_current_page():
            await asyncio.sleep(60.0)
            await self.show_page(self.current_page)

        self.ctx.bot.loop.create_task(go_back_to_current_page())


class FieldMenus(menus.ListPageSource):
    def __init__(self, entries, *, per_page, **kwargs):
        super().__init__(entries, per_page=per_page)

    async def format_page(self, menu, entries) -> discord.Embed:
        embed = discord.Embed()
        for entry in entries:
            embed.add_field(name=entry[0], value=entry[1], inline=False)
        embed.set_footer(text=f"Page {menu.current_page + 1} of {self.get_max_pages()}")
        return embed
