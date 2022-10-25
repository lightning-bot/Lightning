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
from typing import List

import discord
from discord.ext import menus
from sanctum.exceptions import NotFound

from lightning import (ExitableMenu, GuildContext, SelectSubMenu,
                       UpdateableMenu, lock_when_pressed)
from lightning.constants import AUTOMOD_EVENT_NAMES_MAPPING
from lightning.utils.paginator import Paginator

automod_event_options = [discord.SelectOption(label="Message Spam", value="message-spam",
                                              description="Controls how many messages a user can send"),
                         discord.SelectOption(label="Mass Mentions", value="mass-mentions",
                                              description="Controls how many mentions can be contained in 1 message"),
                         discord.SelectOption(label="URL Spam", value="url-spam",
                                              description="Controls how many links can be sent"),
                         discord.SelectOption(label="Invite Spam", value="invite-spam",
                                              description="Controls how many discord.gg invites can be sent"),
                         discord.SelectOption(label="Repetitive Message Spam", value="message-content-spam",
                                              description="Controls how many messages containing the same content can "
                                                          "be sent")]

automod_punishment_options = [discord.SelectOption(label="Delete", value="DELETE", description="Deletes the message"),
                              discord.SelectOption(label="Warn", value="WARN",
                                                   description="Warns the author of the message"),
                              discord.SelectOption(label="Kick", value="KICK",
                                                   description="Kicks the author of the message"),
                              discord.SelectOption(label="Mute", value="MUTE",
                                                   description="Mutes the author of the message"),
                              discord.SelectOption(label="Ban", value="BAN", description="Bans the author of the "
                                                                                         "message")]


async def prompt_for_automod_punishments(ctx: GuildContext):
    prompt = SelectSubMenu(*automod_punishment_options, context=ctx)
    m = await ctx.send("Select a punishment for this rule", view=prompt)
    await prompt.wait()

    await m.delete()

    if not prompt.values:
        await ctx.send("You did not provide a punishment type! Exiting...")
        return

    # We need to ask for duration at some point...

    return prompt.values


class AutoModMassMentionsModal(discord.ui.Modal, title="Automod Configuration"):
    count = discord.ui.TextInput(label="Count", min_length=1, max_length=3)
    # Type should be a select

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.count._value = int(self.count.value)  # type: ignore
        except ValueError:
            await interaction.response.send_message("Count is not a number. For reference, you gave "
                                                    f"{self.count.value}", ephemeral=True)
            return

        # await interaction.client.api.add_automod_config(interaction.guild.id)
        await interaction.response.send_message(f"{self.count.value}", ephemeral=True)


class AutoModEventModal(AutoModMassMentionsModal):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx

    seconds = discord.ui.TextInput(label="Seconds", min_length=1, max_length=3)
    # tfw Discord removed Selects as it's a "bug"
    punishment_type = discord.ui.Select(placeholder="Select a punishment type", options=automod_punishment_options)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.count._value = int(self.count.value)  # type: ignore
        except ValueError:
            await interaction.response.send_message("Count is not a number. For reference, "
                                                    f"you gave {self.count.value}", ephemeral=True)
            return

        try:
            self.seconds._value = int(self.seconds.value)  # type: ignore
        except ValueError:
            # You did not provide a number for the seconds field
            await interaction.response.send_message("Seconds is not a number. For reference, "
                                                    f"you gave {self.seconds.value}", ephemeral=True)
            return

        # await interaction.client.api.add_automod_config(interaction.guild.id)
        await interaction.followup.send(f"{self.seconds.value}", ephemeral=True)


class AutoModConfiguration(ExitableMenu):
    @discord.ui.select(placeholder="Select an event to configure", options=automod_event_options)
    async def configure_automod_event(self, interaction: discord.Interaction, select: discord.ui.Select):
        modal = AutoModEventModal(
            self.ctx) if select.values[0] != "mass-mentions" else AutoModMassMentionsModal(self.ctx)
        await interaction.response.send_modal(modal)


class AutoModSetup(UpdateableMenu, ExitableMenu):
    async def format_initial_message(self, ctx):
        # config = await ctx.bot.api.get_guild_automod_events(ctx.guild.id)
        try:
            config = await ctx.bot.api.get_guild_automod_rules(ctx.guild.id)
        except NotFound:
            return "AutoMod has not been setup yet!"

        fmt = '\n'.join(f"\N{BULLET} {AUTOMOD_EVENT_NAMES_MAPPING[record['type']]}: {record['count']}/"
                        f"{record['seconds']}s"
                        for record in config)

        return f"**AutoMod Configuration**\nActive events:\n{fmt}"

    @discord.ui.button(label="Add new rule", style=discord.ButtonStyle.blurple)
    @lock_when_pressed
    async def add_configuration_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AutoModConfiguration(context=self.ctx)
        await interaction.response.send_message(view=view)
        await view.wait()

    @discord.ui.button(label="Add ignores")
    @lock_when_pressed
    async def add_ignores_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ...

    @discord.ui.button(label="Remove specific rule", style=discord.ButtonStyle.danger)
    @lock_when_pressed
    async def remove_event_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        select = SelectSubMenu(*automod_event_options, context=self.ctx)
        m = await interaction.followup.send("Select the event you want to remove configuration for", view=select,
                                            wait=True)
        await select.wait()
        await m.delete()
        if not select.values:
            return

        # await self.ctx.bot.api.remove_guild_automod_event(self.ctx.guild.id, select.values[0])
        try:
            await self.ctx.bot.api.request("DELETE", f"/guilds/{interaction.guild.id}/automod/rules/{select.values[0]}")
        except NotFound:
            await interaction.followup.send("The automod event you selected is not configured!", ephemeral=True)
            return

        await interaction.followup.send(f"Removed {AUTOMOD_EVENT_NAMES_MAPPING[select.values[0]]} configuration!")


class AutoModIgnoredPages(menus.ListPageSource):
    async def format_page(self, menu: Paginator, entries: List[str]):
        desc = [f'{idx + 1}. {entry}' for idx, entry in enumerate(entries, menu.current_page * self.per_page)]
        return discord.Embed(title="Ignores", description="\n".join(desc), color=discord.Color.greyple())
