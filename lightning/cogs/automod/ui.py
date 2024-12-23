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

import contextlib
import random
from typing import TYPE_CHECKING, Any, List, Optional

import discord
from discord.ext import menus
from sanctum.exceptions import NotFound

from lightning import (BaseView, BasicMenuLikeView, ExitableMenu, GuildContext,
                       LightningBot, SelectSubMenu, UpdateableMenu,
                       lock_when_pressed)
from lightning.constants import AUTOMOD_EVENT_NAMES_MAPPING
from lightning.utils.checks import has_dangerous_permissions
from lightning.utils.paginator import Paginator
from lightning.utils.ui import ConfirmationView

if TYPE_CHECKING:
    from .cog import AutoMod as AutoModCog
    from .models import GateKeeperConfig

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


class AutoModWarnThresholdMigration(discord.ui.View):
    def __init__(self, *, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.choice = None

    async def interaction_check(self, interaction: discord.Interaction):
        return self.author_id == interaction.user.id

    @discord.ui.button(label="Warn Kick")
    async def warn_kick(self, itx: discord.Interaction, button: discord.ui.Button):
        self.choice = "warn_kick"
        await itx.response.edit_message(view=None)
        self.stop()

    @discord.ui.button(label="Warn Ban")
    async def warn_ban(self, itx: discord.Interaction, button: discord.ui.Button):
        self.choice = "warn_ban"
        await itx.response.edit_message(view=None)
        self.stop()


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
