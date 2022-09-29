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
from typing import TYPE_CHECKING

import discord
from sanctum.exceptions import NotFound

from lightning import ExitableMenu, LoggingType, SelectSubMenu, UpdateableMenu
from lightning.constants import AUTOMOD_EVENT_NAMES_MAPPING
from lightning.context import GuildContext
from lightning.converters import Role
from lightning.events import ChannelConfigInvalidateEvent
from lightning.ui import lock_when_pressed

if TYPE_CHECKING:
    from lightning.cogs.config.cog import Configuration


class Logging(UpdateableMenu, ExitableMenu):
    def __init__(self, log_channel: discord.TextChannel, **kwargs):
        super().__init__(**kwargs)
        self.log_channel = log_channel

    def invalidate(self):
        self.ctx.bot.dispatch("lightning_channel_config_remove",
                              ChannelConfigInvalidateEvent(self.log_channel))

    async def fetch_record(self):
        query = "SELECT * FROM logging WHERE guild_id=$1 AND channel_id=$2;"
        record = await self.ctx.bot.pool.fetchrow(query, self.ctx.guild.id, self.log_channel.id)
        return record

    async def update_components(self):
        record = await self.fetch_record()
        if not record:
            self.remove_logging_button.disabled = True
            self.change_format_button.disabled = True
        else:
            self.remove_logging_button.disabled = False
            self.change_format_button.disabled = False

    async def format_initial_message(self, ctx):
        record = await self.fetch_record()
        if not record:
            content = f"No configuration exists for {self.log_channel.mention} yet!"
        else:
            types = LoggingType(record['types'])
            content = f"Configuration for {self.log_channel.mention}:\n\n"\
                      f"Events: {types.to_simple_str().replace('|', ', ')}\n"\
                      f"Log Format: {record['format'].title()}"
        return content

    @discord.ui.button(label="Log all events", style=discord.ButtonStyle.primary, emoji="\N{LEDGER}")
    async def log_all_events_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        query = """INSERT INTO logging (guild_id, channel_id, types)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (channel_id)
                   DO UPDATE SET types = EXCLUDED.types;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id, int(LoggingType.all))
        self.invalidate()
        await self.update(interaction=interaction)

    @discord.ui.button(label="Setup specific logging events", style=discord.ButtonStyle.primary, emoji="\N{OPEN BOOK}")
    async def specific_events_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.lock(interaction=interaction):
            view = SelectSubMenu(*[x.name for x in LoggingType.all], max_options=len(LoggingType.all), context=self.ctx)
            view.add_item(discord.ui.Button(label="Documentation",
                                            url="https://lightning-bot.gitlab.io/bot-configuration/#events"))
            await interaction.response.defer()
            msg = await interaction.followup.send(content='Select the events you wish to log', view=view, wait=True)
            await view.wait()

            if not view.values:
                await msg.delete()
                return

            values = LoggingType.from_simple_str("|".join(view.values))
            query = """INSERT INTO logging (guild_id, channel_id, types)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (channel_id)
                       DO UPDATE SET types = EXCLUDED.types;"""
            await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id, int(values))
            await msg.delete()
            self.invalidate()

    @discord.ui.button(label="Change logging format", style=discord.ButtonStyle.primary, emoji="\N{NOTEBOOK}")
    @lock_when_pressed
    async def change_format_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = SelectSubMenu('emoji', 'minimal with timestamp', 'minimal without timestamp', 'embed', context=self.ctx)
        await interaction.response.defer()
        message = await interaction.followup.send("Select the type of log format to change to", view=view,
                                                  wait=True)
        await view.wait()

        if not view.values:
            await message.delete()
            return

        format_type = view.values[0].lower()
        connection = self.ctx.bot.pool
        query = """UPDATE logging SET format=$1 WHERE guild_id=$2 and channel_id=$3;"""
        await connection.execute(query, format_type, self.log_channel.guild.id,
                                 self.log_channel.id)
        await message.delete()

        self.invalidate()

    @discord.ui.button(label="Remove logging", style=discord.ButtonStyle.red, emoji="\N{CLOSED BOOK}")
    async def remove_logging_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        query = """DELETE FROM logging
                   WHERE guild_id=$1
                   AND channel_id=$2;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id)
        self.invalidate()
        await self.update(interaction=interaction)


class AutoRole(UpdateableMenu, ExitableMenu):
    async def format_initial_message(self, ctx):
        record = await ctx.bot.get_guild_bot_config(ctx.guild.id)
        embed = discord.Embed(title="Auto Role Configuration", color=0xf74b06)

        if record.autorole:
            self.add_autorole_button.label = "Change autorole"
            self.remove_autorole_button.disabled = False
            embed.description = f"Members will be assigned {record.autorole.mention} ({record.autorole.id}) when they"\
                " join this server."
        elif record.autorole_id is None:  # has not been configured
            self.remove_autorole_button.disabled = True
            self.add_autorole_button.label = "Add an autorole"
            embed.description = "This server has not setup an autorole yet."
        else:
            self.remove_autorole_button.disabled = False
            self.add_autorole_button.label = "Change autorole"
            embed.description = "The autorole that was configured seems to be deleted! You can set another up by"\
                                " pressing the \"Change autorole\" button."

        return embed

    @discord.ui.button(label="Add an autorole", style=discord.ButtonStyle.primary)
    @lock_when_pressed
    async def add_autorole_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        content = "What role would you like to setup? You can send the ID, name, or mention of a role."
        role = await self.prompt_convert(interaction, content, Role())

        if not role:
            return

        cog: Configuration = self.ctx.cog
        await cog.add_config_key(self.ctx.guild.id, "autorole", role.id)
        await self.ctx.bot.get_guild_bot_config.invalidate(self.ctx.guild.id)

    @discord.ui.button(label="Remove autorole", style=discord.ButtonStyle.red)
    async def remove_autorole_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.ctx.cog.remove_config_key(self.ctx.guild.id, "autorole")
        await self.ctx.bot.get_guild_bot_config.invalidate(self.ctx.guild.id)
        await interaction.response.send_message(content="Successfully removed the server's autorole")
        await self.update()


class PrefixModal(discord.ui.Modal, title="Add a prefix"):
    prefix = discord.ui.TextInput(label="Prefix", max_length=50, min_length=1)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message()


class Prefix(UpdateableMenu, ExitableMenu):
    async def format_initial_message(self, ctx):
        config = await self.get_prefixes()
        if not config:
            return "No custom prefixes are currently set up!"

        pfxs = "\n".join(f"\N{BULLET} `{pfx}`" for pfx in config)
        return f"**Prefix Configuration**:\n{pfxs}"

    async def update_components(self) -> None:
        config = await self.get_prefixes()
        self.add_prefix.disabled = len(config) > 5
        self.remove_prefix.disabled = not config

    async def get_prefixes(self) -> list:
        try:
            return await self.ctx.bot.api.request("GET", f"/guilds/{self.ctx.guild.id}/prefixes")  # type: ignore
        except NotFound:
            return []

    @discord.ui.button(label="Add prefix", style=discord.ButtonStyle.blurple)
    @lock_when_pressed
    async def add_prefix(self, interaction: discord.Interaction, button: discord.ui.Button):
        prefixes = await self.get_prefixes()
        if len(prefixes) > 5:
            await interaction.response.send_message("You cannot have more than 5 custom prefixes!")
            return

        modal = PrefixModal()
        await interaction.response.send_modal(modal)
        await modal.wait()

        if not modal.prefix.value:
            return

        if modal.prefix.value in prefixes:
            await interaction.followup.send("This prefix is already registered!", ephemeral=True)
            return

        prefixes.append(modal.prefix.value)
        await self.ctx.bot.api.bulk_upsert_guild_prefixes(self.ctx.guild.id, prefixes)

    @discord.ui.button(label="Remove prefix", style=discord.ButtonStyle.danger)
    @lock_when_pressed
    async def remove_prefix(self, interaction: discord.Interaction, button: discord.ui.Button):
        prefixes = await self.get_prefixes()
        await interaction.response.defer()
        select = SelectSubMenu(*prefixes, context=self.ctx)
        m = await interaction.followup.send(view=select, wait=True)
        await select.wait()
        await m.delete()

        if not select.values:
            return

        prefixes.remove(select.values[0])
        await self.ctx.bot.api.bulk_upsert_guild_prefixes(self.ctx.guild.id, prefixes)


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
