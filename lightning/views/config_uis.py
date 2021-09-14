"""
Lightning.py - A Discord bot
Copyright (C) 2019-2021 LightSage

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
import discord

from lightning import ExitableMenu, LoggingType, SelectSubMenu, UpdateableMenu
from lightning.converters import Role
from lightning.events import ChannelConfigInvalidateEvent


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
    async def log_all_events_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        query = """INSERT INTO logging (guild_id, channel_id, types)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (channel_id)
                   DO UPDATE SET types = EXCLUDED.types;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id, int(LoggingType.all))
        self.invalidate()
        # await interaction.response.defer()
        # await interaction.followup.send(f"Successfully set up logging for {self.log_channel.mention}! "
        #                                f"({LoggingType.all.to_simple_str().replace('|', ', ')})")
        await self.update()

    @discord.ui.button(label="Setup specific logging events", style=discord.ButtonStyle.primary, emoji="\N{OPEN BOOK}")
    async def specific_events_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        async with self.lock():
            view = SelectSubMenu(*[x.name for x in LoggingType.all], max_options=len(LoggingType.all))
            view.ctx = self.ctx
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
            # await interaction.followup.send(f"Successfully set up logging for {self.log_channel.mention}! "
            #                                f"({values.to_simple_str().replace('|', ', ')})", ephemeral=True)
            self.invalidate()

    @discord.ui.button(label="Change logging format", style=discord.ButtonStyle.primary, emoji="\N{NOTEBOOK}")
    async def change_format_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        fmts = ['emoji', 'minimal with timestamp', 'minimal without timestamp', 'embed']
        async with self.lock():
            view = SelectSubMenu(*fmts)
            view.ctx = self.ctx
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

        # await interaction.followup.send(f"Successfully changed the log format to {format_type}!")
        self.invalidate()

    @discord.ui.button(label="Remove logging", style=discord.ButtonStyle.red, emoji="\N{CLOSED BOOK}")
    async def remove_logging_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        query = """DELETE FROM logging
                   WHERE guild_id=$1
                   AND channel_id=$2;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id)
        # await interaction.response.defer()
        # await interaction.followup.send(content=f"Removed logging from {self.log_channel.mention}!")
        self.invalidate()
        await self.update()


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
    async def add_autorole_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        async with self.lock():
            await interaction.response.defer()
            content = "What role would you like to setup? You can send the ID, name, or mention of a role."
            role = await self.prompt_convert(interaction, content, Role())

            if not role:
                return

            cog = self.ctx.cog
            await cog.add_config_key(self.ctx.guild.id, "autorole", role.id)
            await self.ctx.bot.get_guild_bot_config.invalidate(self.ctx.guild.id)

    @discord.ui.button(label="Remove autorole", style=discord.ButtonStyle.red)
    async def remove_autorole_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        await self.ctx.cog.remove_config_key(self.ctx.guild.id, "autorole")
        await self.ctx.bot.get_guild_bot_config.invalidate(self.ctx.guild.id)
        await interaction.response.send_message(content="Successfully removed the server's autorole")
        await self.update()
