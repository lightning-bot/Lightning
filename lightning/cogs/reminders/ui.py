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
from __future__ import annotations

import textwrap
from datetime import datetime

import discord
from discord.ext import menus

from lightning.constants import Emoji
from lightning.ui import ExitableMenu, lock_when_pressed
from lightning.utils.paginator import Paginator


class ReminderEditTextModal(discord.ui.Modal):
    def __init__(self, *, title: str = "Edit Reminder", view: ReminderEdit) -> None:
        super().__init__(title=title)
        self.view = view

    text = discord.ui.TextInput(label="Text", style=discord.TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.view.ctx.bot.api.request("PATCH", f"/users/{interaction.user.id}/reminders/{self.view.timer_id}",
                                            data={"reminder_text": self.text.value})
        await interaction.response.send_message("Edited the reminder's text!", ephemeral=True)


class ReminderEdit(ExitableMenu):
    def __init__(self, timer_id: int, *, context):
        super().__init__(context=context, disable_components_after=True, timeout=180)
        self.timer_id = timer_id

    async def format_initial_message(self, ctx):
        record = await ctx.bot.api.get_timer(self.timer_id)
        content = f"**Reminder #{self.timer_id}**:\nExpires: "\
            f"{discord.utils.format_dt(datetime.fromisoformat(record['expiry']))}\nText: "\
            f"{record['extra']['reminder_text']}"

        if ctx.interaction:
            return {"content": content, "ephemeral": True}

        return {"content": content}

    @discord.ui.button(label="Edit Text", emoji="\N{PENCIL}", style=discord.ButtonStyle.blurple)
    async def edit_reminder_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ReminderEditTextModal(view=self)
        await interaction.response.send_modal(modal)
        edited = await modal.wait()
        if edited:
            return

        msg = await self.format_initial_message(self.ctx)
        await interaction.edit_original_response(content=msg['content'])

    @lock_when_pressed
    @discord.ui.button(label="Delete reminder", emoji=Emoji.redtick, style=discord.ButtonStyle.danger)
    async def delete_reminder_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        prompt = await self.ctx.confirm("Are you sure you want to delete this reminder?")
        if prompt is not True:
            return

        await self.ctx.bot.api.delete_timer(self.timer_id)
        await interaction.followup.send("Deleted the reminder!")
        self.stop()

    # At some point we'll have a date picker...


class ReminderSource(menus.ListPageSource):
    def __init__(self, entries):
        super().__init__(entries, per_page=10)

    async def format_page(self, menu: ReminderPaginator, records):
        embed = discord.Embed(title="Reminders", color=0xf74b06)
        for record in records:
            text = textwrap.shorten(record['extra']['reminder_text'], width=512)
            dt = discord.utils.format_dt(datetime.fromisoformat(record['expiry']), style="R")

            embed.add_field(name=f"{record['id']}: {dt}", value=text, inline=False)
        return embed


class ReminderPaginator(Paginator):
    def __init__(self, records, /, *, context):
        super().__init__(ReminderSource(records), context=context, timeout=90)
