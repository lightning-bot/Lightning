"""
Lightning.py - A multi-purpose Discord bot
Copyright (C) 2020 - LightSage

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

import discord
from discord.ext import menus

from lightning.utils.helpers import Emoji


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


class InfoMenuPages(menus.MenuPages):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @menus.button("\N{INFORMATION SOURCE}\ufe0f", position=menus.Last(3))
    async def info_page(self, payload) -> None:
        """shows you this message"""
        messages = ['Welcome to the interactive paginator!\n']
        messages.append('This interactively allows you to see pages of text by navigating with '
                        'reactions. They are as follows:\n')
        for emoji in self.buttons:
            messages.append(f'{str(emoji)} {self.buttons[emoji].action.__doc__}')

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


class Confirmation(menus.Menu):
    """A confirmation menu.

    Parameters
    ----------
    ctx : Context
        The context of the command.
    message : str
        The message to send with the menu.
    timeout : float
        How long to wait for a response before returning.
    delete_message_after : bool
        Whether to delete the message after an option has been selected.
    confirmation_message : bool
        Whether to use the default confirmation message or not.

    Returns
    -------
    Optional[bool]
        ``True`` if explicit confirm,
        ``False`` if explicit deny,
        ``None`` if deny due to timeout
    """

    def __init__(self, ctx, message, *, timeout=30.0, delete_message_after=False, confirmation_message=True):
        super().__init__(timeout=timeout, delete_message_after=delete_message_after)
        self.ctx = ctx
        self.result = None

        if ctx.guild is not None:
            self.permissions = ctx.channel.permissions_for(ctx.guild.me)
        else:
            self.permissions = ctx.channel.permissions_for(ctx.bot.user)

        if not self.permissions.external_emojis:
            # Clear buttons and fallback to the Unicode emojis
            self.clear_buttons()
            confirm = menus.Button("\N{WHITE HEAVY CHECK MARK}", self.do_confirm)
            deny = menus.Button("\N{CROSS MARK}", self.do_deny)
            self.add_button(confirm)
            self.add_button(deny)

        if confirmation_message is True:
            reactbuttons = list(self.buttons.keys())
            self.msg = f"{message}\n\nReact with {reactbuttons[0]} to confirm or"\
                       f" {reactbuttons[1]} to deny."
        else:
            self.msg = message

    async def send_initial_message(self, ctx, channel) -> discord.Message:
        return await channel.send(self.msg)

    @menus.button(Emoji.greentick)
    async def do_confirm(self, payload) -> None:
        self.result = True
        self.stop()

    @menus.button(Emoji.redtick)
    async def do_deny(self, payload) -> None:
        self.result = False
        self.stop()

    async def prompt(self) -> bool:
        await self.start(self.ctx, wait=True)
        return self.result
