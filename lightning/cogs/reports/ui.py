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

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import discord
from sanctum.exceptions import NotFound

from lightning import GuildContext, LightningBot, lock_when_pressed
from lightning.cache import registry as cache_registry
from lightning.ui import BaseView, ExitableMenu, MenuLikeView, UpdateableMenu
from lightning.utils.helpers import dm_user
from lightning.utils.modlogformats import (base_user_format,
                                           construct_dm_message)
from lightning.utils.time import FutureTime, add_tzinfo

if TYPE_CHECKING:
    from lightning.cogs.automod import AutoMod


class ReasonModal(discord.ui.Modal, title="Message Report"):
    reason = discord.ui.TextInput(label='Reason', style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction[LightningBot], /) -> None:
        return await interaction.response.defer()
        # return await interaction.response.send_message("I got your response!", ephemeral=True)


class ActionOptionsModal(discord.ui.Modal, title="Action Options"):
    duration = discord.ui.TextInput(label="Duration", style=discord.TextStyle.short)
    dt = None

    async def on_submit(self, interaction: discord.Interaction[LightningBot]) -> None:
        try:
            self.dt = FutureTime(self.duration.value)
        except Exception as e:
            await interaction.response.send_message(e, ephemeral=True)
            return

        return await interaction.response.defer()


action_options = [discord.SelectOption(label="Delete", value="delete", emoji="<:delete:1099772388448673972>"),
                  discord.SelectOption(label="Warn", value="warn", emoji="\N{WARNING SIGN}"),
                  discord.SelectOption(label="Mute", value="mute", emoji="\N{SPEAKER WITH CANCELLATION STROKE}"),
                  discord.SelectOption(label="Kick", value="kick", emoji="\N{WOMANS BOOTS}"),
                  discord.SelectOption(label="Ban", value="ban", emoji="\N{HAMMER}")]


class ActionDashboard(BaseView):
    def __init__(self, message: discord.Message, *, timeout=180):
        self.message = message
        self.action = None
        self.reason = "No reason provided."
        self.notify = False
        self.duration = None
        super().__init__(timeout=timeout)

    @discord.ui.select(options=action_options, min_values=1, max_values=1, placeholder="Select a punishment")
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.confirm_button.disabled = False
        self.reason_button.disabled = False
        self.notify_button.disabled = False
        self.action = select.values[0]

        if self.action in ("mute", "ban"):
            self.duration_button.disabled = False

        await interaction.response.edit_message(content=f"You selected {self.action.capitalize()}. "
                                                        "Press Confirm once you're done configuring any other options.",
                                                view=self)

    @discord.ui.button(label="Reason", disabled=True, emoji="\N{MEMO}")
    async def reason_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ReasonModal()
        modal.reason.required = True
        modal.reason.default = self.reason
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.reason = modal.reason.value

    @discord.ui.button(label="Duration", disabled=True, emoji="\N{HOURGLASS WITH FLOWING SAND}")
    async def duration_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ActionOptionsModal()
        await interaction.response.send_modal(modal)
        await modal.wait()

        if not modal.dt:
            return

        self.duration = modal.dt.delta

    @discord.ui.button(label="Notify", style=discord.ButtonStyle.blurple, disabled=True, emoji="\N{BELL}")
    async def notify_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        self.notify = not self.notify

        if self.notify:
            content = f"{self.message.author.mention} will receive a DM when you press Confirm."
            self.notify_button.label = "Don't Notify"
        else:
            content = f"{self.message.author.mention} will not receive a DM when you press Confirm."
            self.notify_button.label = "Notify"

        await interaction.response.edit_message(view=self)
        await interaction.followup.send(content, ephemeral=True)

    def member_unactionable(self):
        return self.message.guild.owner_id == self.message.author.id or \
            self.message.guild.me.top_role <= self.message.author.top_role

    def calculate_duration(self):
        return datetime.now(timezone.utc) + self.duration if self.duration else None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, disabled=True, row=2)
    async def confirm_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        # I don't wanna repeat these again
        cog: Optional[AutoMod] = interaction.client.get_cog("AutoMod")
        if not cog:
            await interaction.response.send_message("Unable to action on reports at this time!", ephemeral=True)
            return

        if self.member_unactionable():
            await interaction.response.send_message("Unable to action on the message author due to role hierarchy!",
                                                    ephemeral=True)
            return

        func = getattr(cog, f"_{self.action}_punishment")

        if self.duration:
            args = (self.message, self.calculate_duration())
        else:
            args = (self.message, )

        if self.notify:
            if self.action in ("warn", "mute"):
                v, loc = f"{self.action}ed", "in"
            elif self.action == "kick":
                v, loc = "kicked", "from"
            elif self.action == "ban":
                v, loc = "banned", "from"
            else:
                v, loc = "punished", "in"
            dm_message = construct_dm_message(self.message.author, v, loc, reason=self.reason,
                                              middle=f" due to a message you posted. ({self.message.jump_url})")
            await dm_user(self.message.author, dm_message)

        await func(*args, reason=self.reason)

        await interaction.response.edit_message(content="Successfully completed action!", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message()
        await interaction.delete_original_response()
        self.action = None
        self.stop()


class ReportDashboard(discord.ui.View):
    def __init__(self, message_id: int, guild_id: int, channel_id: int):
        self.dismissed = False
        self.actioned = False
        self.message_id = message_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="View Reported Message",
                                        url=f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
                                        row=1))

        self.action_button.custom_id = f"lightning-reportdash-{message_id}:action"
        self.view_reporters_button.custom_id = f"lightning-reportdash-{message_id}:view"
        self.dismiss_button.custom_id = f"lightning-reportdash-{message_id}:dismiss"

        self.update_buttons()

    @classmethod
    def from_record(cls, record):
        c = cls(record['message_id'], record['guild_id'], record['channel_id'])
        c.dismissed = record['dismissed']
        c.actioned = record['actioned']
        return c

    def update_buttons(self):
        if self.dismissed:
            self.dismiss_button.label = "Re-Open"
            self.dismiss_button.style = discord.ButtonStyle.green
        else:
            self.dismiss_button.label = "Dismiss"
            self.dismiss_button.style = discord.ButtonStyle.red

        self.view_reporters_button.disabled = self.dismissed
        self.action_button.disabled = self.actioned or self.dismissed

    async def fetch_message(self, interaction: discord.Interaction[LightningBot]) -> Optional[discord.Message]:
        channel = interaction.guild.get_channel_or_thread(self.channel_id)
        if not channel:
            return

        return await channel.fetch_message(self.message_id)

    @discord.ui.button(label="Action", style=discord.ButtonStyle.red)
    async def action_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        try:
            msg = await self.fetch_message(interaction)
        except discord.NotFound:
            # Dismiss it?
            await interaction.response.send_message("This message was deleted!", ephemeral=True)
            return

        view = ActionDashboard(msg)
        await interaction.response.send_message(content="Select a punishment below", view=view, ephemeral=True)
        timed_out = await view.wait()
        if timed_out is True or view.action is None:
            return

        self.actioned = True
        await interaction.client.api.edit_guild_message_report(interaction.guild.id, self.message_id,
                                                               {"actioned": True})
        self.update_buttons()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="View Reporters", style=discord.ButtonStyle.blurple)
    async def view_reporters_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        reporters = await interaction.client.api.get_guild_message_reporters(interaction.guild.id, self.message_id)
        tmp = []
        for record in reporters:
            m = interaction.guild.get_member(record['author_id']) or record['author_id']
            timestamp = add_tzinfo(datetime.fromisoformat(record['reported_at']))
            tmp.append(f"\N{BULLET} {discord.utils.format_dt(timestamp)} {base_user_format(m)}: {record['reason']}")

        await interaction.response.send_message("\n".join(tmp), ephemeral=True)

    @discord.ui.button()
    async def dismiss_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        self.dismissed = not self.dismissed
        await interaction.client.api.edit_guild_message_report(interaction.guild.id, self.message_id,
                                                               {"dismissed": self.dismissed})
        self.update_buttons()
        await interaction.response.edit_message(view=self)


class _SelectSM(discord.ui.ChannelSelect['ChannelSelect']):
    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None

        await interaction.response.defer()

        self.view.stop(interaction=interaction)


class ChannelSelect(MenuLikeView):
    def __init__(self,
                 **kwargs):
        super().__init__(**kwargs)
        select = _SelectSM(max_values=1, channel_types=[discord.ChannelType.text],
                           placeholder="Select a channel")
        self.add_item(select)

        self._select = select

    @property
    def values(self):
        return self._select.values or []

    async def cleanup(self, **kwargs) -> None:
        return


class ReportConfiguration(UpdateableMenu, ExitableMenu):
    ctx: GuildContext

    async def format_initial_message(self, ctx: GuildContext):
        try:
            record = await ctx.bot.api.get_guild_moderation_config(ctx.guild.id)
        except NotFound:
            return "You haven't set up message reports yet!"

        if record['message_report_channel_id'] is None:
            return "You haven't set up message reports yet!"

        channel = ctx.guild.get_channel(record['message_report_channel_id'])
        if not channel:
            ...

        return f"**Message Report Configuration**\nReport Channel: <#{record['message_report_channel_id']}>"

    async def update_components(self) -> None:
        try:
            record = await self.ctx.bot.api.get_guild_moderation_config(self.ctx.guild.id)
        except NotFound:
            record = None

        if not record:
            self.set_channel_button.disabled = False
            return

        if self.ctx.guild.get_channel(record['message_report_channel_id']):
            self.set_channel_button.disabled = True

    async def invalidate_config(self, guild_id: int):
        if c := cache_registry.get("mod_config"):
            await c.invalidate(str(guild_id))

    @discord.ui.button(label="Set report channel", style=discord.ButtonStyle.blurple)
    @lock_when_pressed
    async def set_channel_button(self, interaction: discord.Interaction[LightningBot], button: discord.ui.Button):
        content = "What channel would you like to use? You can select the channel below."
        view = ChannelSelect(context=self.ctx)
        await interaction.response.send_message(content, view=view, ephemeral=True)
        await view.wait()
        await interaction.delete_original_response()

        if not view.values:
            return

        channel = view.values[0].resolve()
        if not channel:
            channel = await view.values[0].fetch()

        query = """INSERT INTO guild_mod_config (guild_id, message_report_channel_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET message_report_channel_id = EXCLUDED.message_report_channel_id;"""
        await interaction.client.pool.execute(query, interaction.guild.id, channel.id)
        await self.invalidate_config(interaction.guild.id)

        await self.update()
