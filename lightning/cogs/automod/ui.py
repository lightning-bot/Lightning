"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

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

import contextlib
import random
from typing import TYPE_CHECKING, Any, List, Optional, Union

import discord
from discord.ext import commands, menus
from sanctum.exceptions import DataConflict, NotFound

from lightning import (BaseView, BasicMenuLikeView, ExitableMenu, GuildContext,
                       LightningBot, SelectSubMenu, UpdateableLayoutView,
                       UpdateableMenu)
from lightning.cogs.automod.converters import AutoModDurationResponse
from lightning.constants import AUTOMOD_EVENT_NAMES_MAPPING
from lightning.utils.checks import has_dangerous_permissions
from lightning.utils.paginator import Paginator
from lightning.utils.time import ShortTime
from lightning.utils.ui import ConfirmationView

if TYPE_CHECKING:
    from .cog import AutoMod as AutoModCog
    from .models import GateKeeperConfig, SpamConfig

    class AutoModContext(GuildContext):
        cog: AutoModCog

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

automod_rule_protection = {
    "message-spam": "Blocks bursts of messages sent in a short period.",
    "mass-mentions": "Blocks mention spam in a short burst.",
    "url-spam": "Blocks users from sending too many links.",
    "invite-spam": "Blocks users from sending too many Discord invites.",
    "message-content-spam": "Blocks repeated messages with the same content.",
}

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
    m = await ctx.send("Choose what should happen when this rule is triggered", view=prompt)
    await prompt.wait()

    await m.delete()

    if not prompt.values:
        await ctx.send("No punishment was selected, so the setup was cancelled.")
        return

    # We need to ask for duration at some point...

    return prompt.values


class AutoModMassMentionsModal(discord.ui.Modal, title="Configure the AutoMod Rule"):
    count = discord.ui.TextInput(label="Limit", min_length=1, max_length=3)
    # Type should be a select

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.count._value = int(self.count.value)  # type: ignore
        except ValueError:
            await interaction.response.send_message("Limit is not a whole number. For example, 5, 10, or 15. For reference, you gave "
                                                    f"{self.count.value}", ephemeral=True)
            return

        # await interaction.client.api.add_automod_config(interaction.guild.id)
        await interaction.response.send_message(f"{self.count.value}", ephemeral=True)


class AutoModEventModal(AutoModMassMentionsModal):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx

    seconds = discord.ui.TextInput(label="Time window (seconds)", min_length=1, max_length=3)
    # tfw Discord removed Selects as it's a "bug"
    punishment_type = discord.ui.Select(placeholder="Choose what should happen", options=automod_punishment_options)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.count._value = int(self.count.value)  # type: ignore
        except ValueError:
            await interaction.response.send_message("Limit is not a whole number. For example, 5, 10, or 15.\nFor reference, "
                                                    f"you gave {self.count.value}", ephemeral=True)
            return

        try:
            self.seconds._value = int(self.seconds.value)  # type: ignore
        except ValueError:
            # You did not provide a number for the time-window field
            await interaction.response.send_message("Time window (seconds) is not a whole number. For example, 30, 60, or 120.\n"
                                                    f"For reference, you gave {self.seconds.value}", ephemeral=True)
            return

        # await interaction.client.api.add_automod_config(interaction.guild.id)
        await interaction.response.send_message(f"{self.seconds.value}", ephemeral=True)


class AutoModConfiguration(ExitableMenu):
    @discord.ui.select(placeholder="Select a rule to configure", options=automod_event_options)
    async def configure_automod_event(self, interaction: discord.Interaction, select: discord.ui.Select):
        modal = AutoModEventModal(
            self.ctx) if select.values[0] != "mass-mentions" else AutoModMassMentionsModal()
        await interaction.response.send_modal(modal)


class AutoModIgnoredPages(menus.ListPageSource):
    async def format_page(self, menu: Paginator, entries: List[str]):
        desc = [f'{idx + 1}. {entry}' for idx, entry in enumerate(entries, menu.current_page * self.per_page)]
        return discord.Embed(title="Ignores", description="\n".join(desc), color=discord.Color.greyple())


class UpdatableActionRow(discord.ui.ActionRow):

    def update(self) -> None:
        """Method to update labels or other properties of children."""
        raise NotImplementedError


class AutoModSelectRuleRow(UpdatableActionRow):
    view: 'AutoModInteractiveView'

    @discord.ui.select(placeholder="Select a rule to configure", options=automod_event_options)
    async def configure_automod_rule(self, interaction: discord.Interaction, select: discord.ui.Select):
        if self.view.selected_rule:
            self.view.discard_changes()

        name = AUTOMOD_EVENT_NAMES_MAPPING.get(select.values[0], select.values[0])
        self.configure_automod_rule.placeholder = f"Selected: {name}"
        self.configure_automod_rule.disabled = True

        self.view.selected_rule = select.values[0]
        await self.view.update(interaction=interaction)


class IntervalModal(discord.ui.Modal, title="Configure the Rate Limit"):
    view: 'AutoModInteractiveView'

    messages = discord.ui.TextInput(label="Limit", required=True,
                                    placeholder="How many messages or mentions should trigger AutoMod?")
    seconds = discord.ui.TextInput(label="Time window (seconds)", placeholder="How many seconds should be counted?",
                                   required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            int(self.messages.value)
            int(self.seconds.value)
        except ValueError:
            await interaction.response.send_message("Oops! Please make sure both fields contain whole numbers (like `5` or `60`).", ephemeral=True)
            self.stop()
            return

        await interaction.response.edit_message()
        self.stop()


class ConfigureIntervalButton(discord.ui.Button):
    view: 'AutoModInteractiveView'

    async def callback(self, interaction: discord.Interaction):
        modal = IntervalModal()
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()
        if timed_out:
            return

        self.view.selected_interval = AutoModDurationResponse(int(modal.messages.value), int(modal.seconds.value))
        self.style = discord.ButtonStyle.grey
        await self.view.update(interaction=interaction)


class PunishmentDurationModal(discord.ui.Modal, title="Configure Punishment Duration"):
    view: 'AutoModInteractiveView'

    duration = discord.ui.TextInput(label="Duration", placeholder="How long should the punishment last?", required=True)
    dt = None

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.dt = ShortTime(self.duration.value.strip(" "))
        except commands.BadArgument:
            await interaction.response.send_message("Hmm, that duration format didn't work. "
                                                    "Try something like `30m`, `2h`, `1d`, or `1w`!", ephemeral=True)
            self.stop()
            return

        if self.dt.delta.years or self.dt.delta.months or self.dt.delta.days > 30:
            await interaction.response.send_message("Punishment durations cannot be longer than 30 days.",
                                                    ephemeral=True)
            self.stop()
            return

        await interaction.response.edit_message()
        self.stop()


class ConfigurePunishmentDurationButton(discord.ui.Button):
    view: 'AutoModInteractiveView'

    async def callback(self, interaction: discord.Interaction):
        if self.view.selected_punishment is None:
            await interaction.response.send_message("Hold on! Choose an action first.", ephemeral=True)
            return

        if self.view.selected_punishment not in ("MUTE", "BAN"):
            await interaction.response.send_message("A duration is only available for Mute or Ban. This punishment does not use one.",
                                                    ephemeral=True)
            return

        modal = PunishmentDurationModal()
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()
        if timed_out:
            return

        assert modal.dt is not None

        delta = modal.dt.delta
        self.view.selected_punishment_duration = (delta.days * 86400 + delta.hours * 3600 + delta.minutes * 60
                                                  + delta.seconds)
        self.style = discord.ButtonStyle.grey
        await self.view.update(interaction=interaction)


class ConfigurePunishmentActionRow(discord.ui.ActionRow):
    view: 'AutoModInteractiveView'

    @discord.ui.select(placeholder="Choose what should happen", options=automod_punishment_options, max_values=1,
                       min_values=1)
    async def punishment_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.view.selected_punishment = select.values[0]
        if self.view.selected_punishment not in ("MUTE", "BAN"):
            self.view.selected_punishment_duration = None
        self.punishment_type.placeholder = f"Selected action: {select.values[0]}"
        self.view.updated_configuration = True
        await self.view.update(interaction=interaction)


class AutoModConfigureRule(discord.ui.ActionRow):
    view: 'AutoModInteractiveView'

    @discord.ui.button(label="Configure Rate Limit", style=discord.ButtonStyle.blurple)
    async def configure_automod_rule(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = IntervalModal()
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()
        if timed_out:
            return

        self.view.selected_interval = AutoModDurationResponse(int(modal.messages.value), int(modal.seconds.value))
        self.configure_automod_rule.style = discord.ButtonStyle.grey
        await self.view.update(interaction=interaction)


class SaveActionRow(discord.ui.ActionRow):
    view: 'AutoModInteractiveView'

    @discord.ui.button(label="Save", style=discord.ButtonStyle.green, disabled=True)
    async def save_changes(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.view
        if view.selected_interval is None:
            await interaction.response.send_message("Not quite! Set the rate limit for this rule first.",
                                                    ephemeral=True)
            return

        if view.selected_punishment is None:
            await interaction.response.send_message("Almost there! Choose an action for this rule.",
                                                    ephemeral=True)
            return

        assert interaction.guild is not None
        assert view.selected_rule is not None
        guild_id = interaction.guild.id
        punishment_payload: dict[str, Union[str, int]] = {"type": view.selected_punishment}
        if view.selected_punishment_duration is not None:
            punishment_payload["duration"] = view.selected_punishment_duration

        payload = {"guild_id": guild_id,
                   "type": view.selected_rule,
                   "count": view.selected_interval.count,
                   "seconds": view.selected_interval.seconds,
                   "punishment": punishment_payload}
        action = "Created"
        try:
            await view.ctx.bot.api.create_guild_automod_rule(guild_id, payload)
        except DataConflict:
            await view.ctx.bot.api.delete_guild_automod_rule(guild_id, view.selected_rule)
            await view.ctx.bot.api.create_guild_automod_rule(guild_id, payload)
            action = "Updated"

        await view.ctx.cog.get_automod_config.invalidate(guild_id)

        rule_name = AUTOMOD_EVENT_NAMES_MAPPING.get(view.selected_rule,
                                                    view.selected_rule.replace("-", " ").title())
        punishment_name = view.selected_punishment.capitalize()
        duration = (f" for {view.selected_punishment_duration} seconds"
                    if view.selected_punishment_duration is not None else "")
        summary = (f"**{rule_name}**\n"
                   f"Trigger: {view.selected_interval.count} "
                   f"{view.interval_unit()} in "
                   f"{view.selected_interval.seconds:g} seconds\n"
                   f"Action: {punishment_name}{duration}")
        await interaction.response.send_message(f"✓ {action} AutoMod rule successfully.\n\n{summary}", ephemeral=True)
        view.discard_changes()
        await view.update()

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red, disabled=True)
    async def delete_rule(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.view
        assert view.selected_rule is not None
        rule_name = AUTOMOD_EVENT_NAMES_MAPPING.get(
            view.selected_rule, view.selected_rule.replace("-", " ").title())
        content = f"Are you sure you want to permanently delete the **{rule_name}** rule?"
        confirmation = ConfirmationView(content, author_id=interaction.user.id)
        await interaction.response.send_message(content, view=confirmation, ephemeral=True)
        await confirmation.wait()

        if confirmation.value is not True:
            return

        assert interaction.guild is not None
        try:
            await view.ctx.bot.api.delete_guild_automod_rule(interaction.guild.id, view.selected_rule)
        except NotFound:
            await interaction.followup.send(f"The **{rule_name}** rule no longer exists.", ephemeral=True)
        else:
            await view.ctx.cog.get_automod_config.invalidate(interaction.guild.id)
            view.discard_changes()
            await interaction.followup.send(f"✓ Deleted the **{rule_name}** AutoMod rule.", ephemeral=True)
            await view.update()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_changes(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.view
        view.discard_changes()
        await view.update(interaction=interaction)
        await interaction.followup.send("✓ Changes discarded. Let's start fresh!", ephemeral=True)


class AutoModInteractiveView(UpdateableLayoutView):
    container = discord.ui.Container(accent_color=discord.Color.blurple())
    selected_rule: Optional[str] = None
    selected_interval: Optional[AutoModDurationResponse] = None
    selected_punishment: Optional[str] = None
    selected_punishment_duration: Optional[int] = None
    setup_settings: bool = False
    sections: dict[str, discord.ui.Section] = {}
    updated_configuration: bool = False

    async def get_configuration(self):
        # assert isinstance(self.ctx.cog, 'AutoModCog')

        return await self.ctx.cog.get_automod_config(self.ctx.guild.id)

    def interval_unit(self) -> str:
        return "mentions" if self.selected_rule == "mass-mentions" else "messages"

    def build_components(self):
        title = "# Let's set up AutoMod\n\nChoose a rule below to create it or update its current settings. "\
            "You'll be able to review the rule before saving your changes."
        self.container.add_item(discord.ui.TextDisplay(title))
        self.container.add_item(discord.ui.Separator())
        # ----Interactive AutoMod-----
        # Select a rule to setup or change configuration
        # SELECT HERE
        # Once, a rule is selected, settings are dropped down
        self.container.add_item(AutoModSelectRuleRow())

    async def start(self, *, wait: bool = True):
        await self.add_initial_components()

        return await super().start(wait=wait)

    async def add_initial_components(self):
        self.build_components()

    def discard_changes(self):
        """Discards the changes and rebuilds the view."""
        self.selected_rule = None
        self.selected_interval = None
        self.selected_punishment = None
        self.selected_punishment_duration = None
        self.setup_settings = False
        self.sections.clear()

        for child in self.container.walk_children():
            self.container.remove_item(child)

        self.build_components()

    async def update_components(self) -> None:
        if not self.selected_rule:
            return

        config = await self.get_configuration()
        cfg: Optional[SpamConfig] = getattr(config, self.selected_rule.replace("-", "_"), None)
        if cfg and not self.setup_settings:
            # We assume that there's already a cooldown configured...
            self.selected_interval = AutoModDurationResponse(cfg.cooldown.rate, cfg.cooldown.per.total_seconds())
            self.selected_punishment = cfg.punishment.type.name
            self.selected_punishment_duration = (int(cfg.punishment.duration)
                                                 if cfg.punishment.duration else None)

        if not cfg:
            ...
            # Not sure why we're returning here
            # return

        if self.setup_settings:
            # We have already built the configuration components, so we just update as needed
            if self.selected_interval:
                new_interval = (f"{self.selected_interval.count} {self.interval_unit()} in "
                                f"{self.selected_interval.seconds:g} seconds")
                if cfg:
                    current_interval = (f"{cfg.cooldown.rate} {self.interval_unit()} in "
                                        f"{cfg.cooldown.per.total_seconds():g} seconds")
                    interval_content = (f"**Currently: {current_interval}**\n"
                                        f"**After saving: {new_interval}**")
                else:
                    interval_content = f"**This rule will use: {new_interval}**"
                self.sections['interval'].children[0].content = interval_content

            punishment_content = "Choose a punishment type to continue."
            if self.selected_punishment:
                new_punishment = self.selected_punishment.capitalize()
                if self.selected_punishment_duration is not None:
                    new_punishment += f" for {self.selected_punishment_duration} seconds"

                if cfg:
                    current_punishment = cfg.punishment.type.name.capitalize()
                    if cfg.punishment.duration:
                        current_punishment += f" for {int(cfg.punishment.duration)} seconds"
                    punishment_content = (f"**Currently: {current_punishment}**\n"
                                          f"**After saving: {new_punishment}**")
                else:
                    punishment_content = f"**This rule will use: {new_punishment}**"
            self.sections['punishment'].children[0].content = punishment_content

            for child in self.container.children:
                if isinstance(child, SaveActionRow):
                    child.children[0].disabled = (self.selected_interval is None or
                                                  self.selected_punishment is None)
                    child.children[0].label = "Save" if cfg else "Create"
                    child.children[1].disabled = cfg is None
                    child.children[2].label = "Cancel"
            return

        rule_name = AUTOMOD_EVENT_NAMES_MAPPING.get(
            self.selected_rule, self.selected_rule.replace("-", " ").title())
        protection = automod_rule_protection.get(
            self.selected_rule, "Helps protect your server from unwanted activity.")
        self.container.add_item(discord.ui.TextDisplay(f"### {rule_name}\n"
                                                       f"-# Protects against: {protection}"))

        # Configure AutoMod Rule Interval
        self.container.add_item(discord.ui.Separator())

        interval_noun = "mention" if self.selected_rule == "mass-mentions" else "message"
        sec_content = f"Choose how often this rule should trigger by setting a {interval_noun} limit and time window."
        if cfg:
            sec_content += f"\n**Currently: {cfg.cooldown.rate} {self.interval_unit()} in "\
                           f"{cfg.cooldown.per.total_seconds()} seconds**"
        section = discord.ui.Section(discord.ui.TextDisplay(sec_content),
                                     accessory=ConfigureIntervalButton(label="Configure Rate Limit"))
        self.sections['interval'] = section
        self.container.add_item(section)

        self.container.add_item(discord.ui.Separator())

        # Configure AutoMod Rule Punishment
        self.container.add_item(discord.ui.TextDisplay("### What should AutoMod do?\n"))
        self.container.add_item(ConfigurePunishmentActionRow())
        # Update the punishment duration button based on existing config
        sec_content = "Choose what happens when this rule is triggered. Mute and Ban actions can also have a duration."
        if cfg:
            sec_content += f"\n**Currently: {cfg.punishment.type.name.capitalize()}**"
        section = discord.ui.Section(discord.ui.TextDisplay(sec_content),
                                     accessory=ConfigurePunishmentDurationButton(label="Configure Punishment Duration"))
        self.sections['punishment'] = section
        self.container.add_item(section)
        # ---
        # Ending menu
        self.container.add_item(discord.ui.Separator())
        rule_name = AUTOMOD_EVENT_NAMES_MAPPING.get(self.selected_rule, self.selected_rule.replace("-", " ").title())
        cancel_action = "discard your changes" if cfg else "exit without creating it"
        self.container.add_item(discord.ui.TextDisplay("Review your settings below. When everything looks right, "
                                                       f"select {'Save' if cfg else 'Create'}. Select Cancel to "
                                                       f"{cancel_action}."))
        save_row = SaveActionRow()
        save_row.children[0].label = "Save" if cfg else "Create"
        save_row.children[1].disabled = cfg is None
        self.container.add_item(save_row)

        # We have built the components for the rule configuration, so we set this to true so we don't do it again.
        self.setup_settings = True


class FakeCtx:
    def __init__(self, member) -> None:
        self.author = member


class GatekeeperRoleView(BasicMenuLikeView):
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select a role", min_values=1, max_values=1)
    async def callback(self, itx: discord.Interaction[LightningBot], select: discord.ui.RoleSelect):
        assert itx.guild is not None

        role = select.values[0]

        if role >= itx.guild.me.top_role:
            await itx.response.send_message("You cannot use this role because it is higher than my role!",
                                            ephemeral=True)
            return

        if has_dangerous_permissions(role.permissions):
            await itx.response.send_message("You cannot use this role because it contains permissions that are deemed"
                                            " dangerous!", ephemeral=True)
            return

        await self.insert_role(itx, role)

        view = ConfirmationView(message="", author_id=itx.user.id, delete_message_after=True)
        await itx.response.send_message(f"Set {role.name} ({role.mention}) as the gatekeeper role!"
                                        "In order for this role to work correctly, you must set permission"
                                        " overrides for every channel. Would you like me to this for you?",
                                        view=view, ephemeral=True)
        await view.wait()
        if view.value is False:
            # a message here
            self.stop(interaction=itx)
            return

        s, f, sk = await self.create_permission_overwrites(itx.guild, role)
        if f >= 1:
            content = f"Set {s+sk} permissions overwrites for this role. {f} channels failed to set permission "\
                      "overrides!"
        else:
            content = f"Set {s+sk} permission overwrites for this role."

        await itx.followup.send(content=content, ephemeral=True)

        self.stop(interaction=itx)

    async def insert_role(self, interaction: discord.Interaction[LightningBot], role: discord.Role):
        query = """INSERT INTO guild_gatekeeper_config (guild_id, role_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET role_id=EXCLUDED.role_id;"""
        await interaction.client.pool.execute(query, role.guild.id, role.id)

    @staticmethod
    async def create_permission_overwrites(guild: discord.Guild, role: discord.Role):
        success = 0
        failure = 0
        skipped = 0
        for channel in guild.channels:
            if channel.permissions_for(guild.me).manage_roles:
                overwrite = channel.overwrites_for(role)
                overwrite.read_messages = False
                overwrite.send_messages = False
                overwrite.add_reactions = False
                overwrite.create_public_threads = False
                overwrite.create_private_threads = False
                overwrite.send_messages_in_threads = False
                overwrite.use_application_commands = False
                try:
                    await channel.set_permissions(role, overwrite=overwrite,
                                                  reason='Creating permission overwrites for the gatekeeper role')
                except discord.HTTPException:
                    failure += 1
                else:
                    success += 1
            else:
                skipped += 1
        return success, failure, skipped

    @discord.ui.button(label="Create a new role")
    async def create_new_role(self, itx: discord.Interaction[LightningBot], button: discord.ui.Button):
        try:
            role = await itx.guild.create_role(name="Pending Verification",
                                               reason=f"Requested role creation by {itx.user}")
        except discord.Forbidden:
            await itx.response.send_message("Unable to create a role because I am missing the Manage Roles permission!",
                                            ephemeral=True)
            return

        await self.insert_role(itx, role)
        view = ConfirmationView(message="", author_id=itx.user.id, delete_message_after=True)
        await itx.response.edit_message(content="Created a new role. In order for this role to work "
                                        "correctly, you must set permission overrides for every channel. "
                                        "Would you like me to do this automatically?", view=view)
        await view.wait()
        if view.value is False:
            # a message here
            return

        s, f, sk = await self.create_permission_overwrites(itx.guild, role)
        if f >= 1:
            content = f"Set {s+sk} permissions overwrites for this role. {f} channels failed to set permission "\
                      "overrides!"
        else:
            content = f"Set {s+sk} permission overwrites for this role."

        await itx.followup.send(content=content, ephemeral=True)
        self.stop(interaction=itx)


class GatekeeperChannelView(BasicMenuLikeView):
    def __init__(self, role: discord.Role, channel: Optional[discord.TextChannel] = None, *,
                 author_id: int, clear_view_after=False, delete_message_after=False,
                 disable_components_after=True, timeout: float | None = 180):
        super().__init__(author_id=author_id,
                         clear_view_after=clear_view_after,
                         delete_message_after=delete_message_after,
                         disable_components_after=disable_components_after,
                         timeout=timeout)
        self.role = role
        self.channel = channel

        if channel:
            self.select_callback.default_values = [channel]

    @discord.ui.select(cls=discord.ui.ChannelSelect,
                       channel_types=[discord.ChannelType.text, discord.ChannelType.private],
                       min_values=1, max_values=1)
    async def select_callback(self, itx: discord.Interaction[LightningBot], select: discord.ui.ChannelSelect):
        channel = select.values[0].resolve()
        await itx.response.defer()
        if not channel:
            await itx.followup.send("Unable to set the verification channel. Please try again!", ephemeral=True)
            return

        query = """INSERT INTO guild_gatekeeper_config (guild_id, verification_channel_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET verification_channel_id=EXCLUDED.verification_channel_id;"""
        await itx.client.pool.execute(query, itx.guild_id, channel.id)
        confirm = ConfirmationView("", author_id=itx.user.id)
        msg = await itx.followup.send(f"Set the verification channel to {channel.mention}! Would you like me to "
                                      "set up the channel permissions for you? Gatekeeper requires that everyone "
                                      f"cannot read this channel, only the {self.role.mention} can read messages",
                                      view=confirm, ephemeral=True, wait=True)
        await confirm.wait()
        if not confirm.value:
            return

        try:
            # Since this is becoming a private channel, I need to give the bot access to the channel beforehand
            overwrite = channel.overwrites_for(itx.guild.me)
            overwrite.read_messages = True
            overwrite.send_messages = True
            overwrite.manage_channels = True
            await channel.set_permissions(itx.guild.me, overwrite=overwrite)
            # Now we set permissions for at-everyone role
            default_p = channel.permissions_for(itx.guild.default_role)
            if default_p.read_messages:
                overwrites = channel.overwrites_for(itx.guild.default_role)
                overwrites.read_messages = False
                await channel.set_permissions(itx.guild.default_role, overwrite=overwrites)
            # Set permissions for the configured join role
            if channel.permissions_for(self.role).read_messages is False:
                overwrite = channel.overwrites_for(self.role)
                overwrite.read_messages = True
                overwrite.read_message_history = True  # sometimes a lil' silly permissions
                overwrite.send_messages = False
                overwrite.add_reactions = False
                overwrite.create_public_threads = False
                overwrite.create_private_threads = False
                overwrite.send_messages_in_threads = False
                overwrite.use_application_commands = False
                await channel.set_permissions(self.role, overwrite=overwrite)
        except discord.HTTPException as e:
            await msg.edit(content=f"Unable to set channel permissions ({e})", view=None)
            self.stop(interaction=itx)
            return

        await msg.edit(content="Set the correct permissions for the verification channel!", view=None)
        self.stop(interaction=itx)


class GatekeeperMessageModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Set Gatekeeper Message")

    message = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=500,
                                   default="This server requires you to verify yourself before you can talk!")

    async def on_submit(self, interaction: discord.Interaction[LightningBot]) -> None:
        await interaction.response.edit_message()


class GatekeeperTypeSetup(BasicMenuLikeView):
    rtype = "basic"

    @discord.ui.button(label="Basic", style=discord.ButtonStyle.blurple)
    async def basic(self, itx: discord.Interaction[LightningBot], button: discord.ui.Button):
        query = """
                INSERT INTO guild_gatekeeper_config (guild_id, honeypot)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET honeypot=EXCLUDED.honeypot;
                """
        await itx.client.pool.execute(query, itx.guild_id, False)

        await itx.response.edit_message()
        self.stop(interaction=itx)

    @discord.ui.button(label="Honeypot", style=discord.ButtonStyle.blurple)
    async def honeypot(self, itx: discord.Interaction[LightningBot], button: discord.ui.Button):
        query = """
                INSERT INTO guild_gatekeeper_config (guild_id, honeypot)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET honeypot=EXCLUDED.honeypot;
                """
        await itx.client.pool.execute(query, itx.guild_id, True)

        await itx.response.edit_message()
        self.rtype = "honeypot"
        self.stop(interaction=itx)


class GatekeeperSetup(UpdateableMenu, ExitableMenu):
    ctx: AutoModContext
    record: dict[str, Any]

    def __init__(self, gatekeeper: Optional[GateKeeperConfig] = None, *, context: AutoModContext):
        super().__init__(context=context,
                         delete_message_after=True,
                         timeout=180)

        self.gatekeeper: Optional[GateKeeperConfig] = gatekeeper

    async def format_initial_message(self, ctx: GuildContext):
        query = "SELECT * FROM guild_gatekeeper_config WHERE guild_id=$1;"
        record = await ctx.bot.pool.fetchrow(query, ctx.guild.id)
        self.record = record

        setup_buttons = (self.set_gatekeeper_role, self.set_gatekeeper_channel)

        if record and record['active']:
            text = "Lightning Gatekeeper is currently active and will gatekeep every new member that joins!\n"\
                   f"__**Type**__: {self.gatekeeper.type.name.capitalize()}\n\n"\
                   f"**Verification Role**: {self.gatekeeper.role.mention}\n"\
                   f"**Verification Channel**: {self.gatekeeper.verification_channel.mention}"
            for button in setup_buttons:
                button.disabled = True
            self.set_switch_labels(True)
            return text

        self.send_verification_message.disabled = True

        if record is None:
            text = "Lightning Gatekeeper is not fully set up!"
            self.set_gatekeeper_role.disabled = False
            self.set_gatekeeper_channel.disabled = True
            self.disable_gatekeeper.disabled = True
            self.set_gatekeeper_type_button.disabled = True
            return text
        elif record['role_id'] is None:
            text = "Lightning Gatekeeper is not fully set up!"
            self.disable_gatekeeper.disabled = True
            self.set_gatekeeper_channel.disabled = True
            self.set_gatekeeper_type_button.disabled = True
            self.set_switch_labels(False)
            return text
        elif record['verification_channel_id'] is None:
            text = "Lightning Gatekeeper is not fully set up!"
            self.set_gatekeeper_role.disabled = True
            self.disable_gatekeeper.disabled = True
            self.set_gatekeeper_channel.disabled = False
            self.set_gatekeeper_type_button.disabled = False
            self.set_switch_labels(False)
            return text
        elif record['active'] is False:
            text = "Lightning Gatekeeper is currently disabled!\n"\
                   "*Click the Enable button to enable the gatekeeper for everyone*"
            self.disable_gatekeeper.disabled = False
            for button in setup_buttons:
                button.disabled = False
            self.set_switch_labels(False)

        if record['verification_channel_id'] and record['role_id']:
            self.disable_gatekeeper.disabled = False
            self.send_verification_message.disabled = False

        return text

    def invalidate_gatekeeper_cache(self):
        self.ctx.cog.invalidate_gatekeeper(self.ctx.guild.id)

    def set_switch_labels(self, status: bool):
        if status:
            self.disable_gatekeeper.label = "Disable"
            self.disable_gatekeeper.style = discord.ButtonStyle.red
        else:
            self.disable_gatekeeper.label = "Enable"
            self.disable_gatekeeper.style = discord.ButtonStyle.green

    @discord.ui.button(label="Set a gatekeeper role", style=discord.ButtonStyle.blurple)
    async def set_gatekeeper_role(self, itx: discord.Interaction[LightningBot], button: discord.ui.Button):
        view = GatekeeperRoleView(author_id=itx.user.id, clear_view_after=True)
        await itx.response.send_message(content='Select a role from the select menu below or '
                                        'create a new role by clicking the "Create a New Role" button',
                                        view=view, ephemeral=True)
        await view.wait()
        self.invalidate_gatekeeper_cache()
        await self.update(interaction=itx)

    @discord.ui.button(label="Set a verification channel", style=discord.ButtonStyle.blurple)
    async def set_gatekeeper_channel(self, itx: discord.Interaction[LightningBot], button: discord.ui.Button):
        if self.gatekeeper and self.gatekeeper.verification_channel_id:
            channel = self.gatekeeper.verification_channel
            role = self.gatekeeper.role
        else:
            channel = None
            role = itx.guild.get_role(self.record['role_id'])

        if role is None:
            await itx.response.send_message("Somehow you clicked this button without setting a role first!",
                                            ephemeral=True)
            return

        view = GatekeeperChannelView(role, channel,
                                     author_id=itx.user.id, delete_message_after=True)
        await itx.response.send_message(content='Select a channel from the select menu below',
                                        view=view, ephemeral=True)
        await view.wait()
        self.invalidate_gatekeeper_cache()
        await self.update(interaction=itx)

    @discord.ui.button(label="Send verification message", style=discord.ButtonStyle.blurple)
    async def send_verification_message(self, itx: discord.Interaction[LightningBot], button: discord.ui.Button):
        self.gatekeeper = await self.ctx.cog.get_gatekeeper_config(itx.guild_id)  # type: ignore
        if self.gatekeeper is None:
            await itx.response.send_message("Somehow your gatekeeper isn't setup correctly!",
                                            ephemeral=True)
            return

        ch = self.gatekeeper.verification_channel
        if ch is None:
            await itx.response.send_message("Please set a verification channel before setting this up!", ephemeral=True)
            return

        modal = GatekeeperMessageModal()
        await itx.response.send_modal(modal)
        await modal.wait()

        embed = discord.Embed(title="Verification Required",
                              description=modal.message.value,
                              color=discord.Color(0xf74b06))
        embed.set_footer(text="This message was set up by the moderators of this server! "
                              "This bot will never ask for your personal information and will not "
                              "redirect you to any external links!")

        view = discord.ui.View(timeout=None)
        cls = GatekeeperVerificationHoneyPotButton if self.gatekeeper.is_honeypot() else GatekeeperVerificationButton
        view.add_item(cls(self.gatekeeper))

        if self.gatekeeper.verification_message_id:
            try:
                og_msg = await ch.fetch_message(self.gatekeeper.verification_message_id)
            except discord.HTTPException:
                og_msg = None

            if og_msg:
                try:
                    await og_msg.edit(embed=embed, view=view)
                except discord.Forbidden:
                    with contextlib.suppress(discord.HTTPException):
                        await og_msg.delete()
                else:
                    await itx.followup.send("Edited the current verification message!", ephemeral=True)
                    return

        try:
            msg = await ch.send(embed=embed, view=view)
        except discord.HTTPException as e:
            await itx.followup.send(f"I was unable to send the verification message. ({e})", ephemeral=True)
            return

        query = """INSERT INTO guild_gatekeeper_config (guild_id, verification_message_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET verification_message_id=EXCLUDED.verification_message_id;"""
        await itx.client.pool.execute(query, itx.guild_id, msg.id)
        # Invalidate and force creation again
        self.invalidate_gatekeeper_cache()
        self.gatekeeper = await self.ctx.cog.get_gatekeeper_config(itx.guild_id)  # type: ignore

        await itx.followup.send("Sent the verification message!", ephemeral=True)

    @discord.ui.button(label="Set gatekeeper type", style=discord.ButtonStyle.blurple)
    async def set_gatekeeper_type_button(self, itx: discord.Interaction[LightningBot], button: discord.ui.Button):
        self.gatekeeper = await self.ctx.cog.get_gatekeeper_config(itx.guild_id)  # type: ignore
        if self.gatekeeper is None:
            await itx.response.send_message("Somehow your gatekeeper isn't setup correctly!",
                                            ephemeral=True)
            return

        view = GatekeeperTypeSetup(author_id=itx.user.id)
        await itx.response.send_message(content="Select the type of gatekeeper you want.",
                                        view=view, ephemeral=True)
        await view.wait()

        try:
            await itx.delete_original_response()
        except Exception:
            pass

        self.invalidate_gatekeeper_cache()
        self.gatekeeper = await self.ctx.cog.get_gatekeeper_config(itx.guild_id)  # type: ignore

        if self.gatekeeper.verification_message_id:
            ch = self.gatekeeper.verification_channel
            if ch:
                try:
                    og_msg = await ch.fetch_message(self.gatekeeper.verification_message_id)
                except discord.HTTPException:
                    og_msg = None

                if og_msg:
                    try:
                        await og_msg.edit(view=view)
                    except discord.HTTPException:
                        ...
        await self.update(interaction=itx)

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.red)
    async def disable_gatekeeper(self, itx: discord.Interaction[LightningBot], button: discord.ui.Button):
        self.gatekeeper = await self.ctx.cog.get_gatekeeper_config(itx.guild_id)  # type: ignore
        if self.gatekeeper is None:
            await itx.response.send_message("Somehow your gatekeeper isn't setup correctly!",
                                            ephemeral=True)
            return

        if button.style is discord.ButtonStyle.green:
            await self.gatekeeper.enable()
            await itx.response.send_message("Enabled the gatekeeper. Every new member will be required to verify.",
                                            ephemeral=True)
            # self.gatekeeper.active_since = datetime.now()
        else:
            await self.gatekeeper.disable()
            query = "UPDATE guild_gatekeeper_config SET active='f' WHERE guild_id=$1;"
            await itx.client.pool.execute(query, itx.guild_id)
            await itx.response.send_message("Disabled the gatekeeper. Removing members from the queue could take some "
                                            "time!", ephemeral=True)

        await self.update(interaction=itx)


# This view is per person and ephemeral
class GatekeeperVerificationHoneyPotView(BaseView):
    def __init__(self, *, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        gb = discord.ui.Button(style=discord.ButtonStyle.grey, label="Confirm")
        gb.callback = self.good_callback

        def create_bad_button():
            button = discord.ui.Button(style=discord.ButtonStyle.danger, label="DO NOT CLICK THIS!")
            button.callback = self.bad_callback
            return button

        buttons = [gb]
        for _ in range(random.randint(1, 8)):
            buttons.append(create_bad_button())

        random.shuffle(buttons)
        for button in buttons:
            self.add_item(button)

        self.safe = None

    async def good_callback(self, interaction: discord.Interaction[LightningBot]):
        self.safe = True
        await interaction.response.edit_message()
        self.stop()

    async def bad_callback(self, interaction: discord.Interaction[LightningBot]):
        self.safe = False
        await interaction.response.send_message("You failed the test!", ephemeral=True)
        self.stop()


class _BaseGatekeeperVerificationButton:
    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction[LightningBot],
                             item: discord.ui.Button, match) -> GatekeeperVerificationButton:
        cog: Optional[AutoModCog] = interaction.client.get_cog("AutoMod")  # type: ignore
        if not cog:
            await interaction.response.send_message("Somehow the Gatekeeper is not working at this moment!",
                                                    ephemeral=True)
            return

        gatekeeper = await cog.get_gatekeeper_config(interaction.guild_id)
        return cls(gatekeeper)

    async def interaction_check(self, interaction: discord.Interaction[LightningBot]) -> bool:
        if self.gatekeeper is None or self.gatekeeper.active is False:
            await interaction.response.send_message("The gatekeeper is not enabled!", ephemeral=True)
            return False

        return True


class GatekeeperVerificationButton(_BaseGatekeeperVerificationButton,
                                   discord.ui.DynamicItem[discord.ui.Button],
                                   template='lightning:gatekeeper:verification:button'):
    def __init__(self, gatekeeper: Optional[GateKeeperConfig] = None) -> None:
        item = discord.ui.Button(style=discord.ButtonStyle.green, label="Verify Me",
                                 custom_id="lightning:gatekeeper:verification:button")
        super().__init__(item)
        self.gatekeeper = gatekeeper

    async def callback(self, interaction: discord.Interaction[LightningBot]) -> None:
        await self.gatekeeper.remove_member(interaction.user)
        await interaction.response.send_message("Thanks for verifying yourself! Access will be granted momentarily",
                                                ephemeral=True)


class GatekeeperVerificationHoneyPotButton(_BaseGatekeeperVerificationButton,
                                           discord.ui.DynamicItem[discord.ui.Button],
                                           template="lightning:gatekeeper:verification:honeypot:button"):
    def __init__(self, gatekeeper: Optional[GateKeeperConfig] = None) -> None:
        item = discord.ui.Button(style=discord.ButtonStyle.green, label="Verify Me",
                                 custom_id="lightning:gatekeeper:verification:honeypot:button")
        super().__init__(item)
        self.gatekeeper = gatekeeper

    async def callback(self, interaction: discord.Interaction[LightningBot]) -> None:
        view = GatekeeperVerificationHoneyPotView(timeout=180)
        await interaction.response.send_message(content="Click the correct button to pass!", ephemeral=True,
                                                view=view)
        await view.wait()

        try:
            await interaction.delete_original_response()
        except Exception:
            pass

        if not view.safe:
            try:
                await interaction.user.kick(reason="Failed to pass honeypot gatekeeper!")
            except discord.HTTPException as e:
                interaction.client.dispatch("lightning_guild_alert",
                                            interaction.guild_id,
                                            f"\N{OCTAGONAL SIGN} Failed to kick @{interaction.user} "
                                            f"(ID: {interaction.user.id}) for failure to "
                                            f"pass the gatekeeper!\n-# ({e})")
            return

        await self.gatekeeper.remove_member(interaction.user)
        await interaction.followup.send(content="Thanks for verifying yourself! Access will be granted momentarily",
                                        ephemeral=True)
