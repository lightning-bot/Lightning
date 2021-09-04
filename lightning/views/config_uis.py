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
from lightning.events import ChannelConfigInvalidateEvent


class Logging(UpdateableMenu, ExitableMenu):
    def __init__(self, log_channel: discord.TextChannel, **kwargs):
        super().__init__(**kwargs)
        self.log_channel = log_channel

    def invalidate(self):
        self.ctx.bot.dispatch("lightning_channel_config_remove",
                              ChannelConfigInvalidateEvent(self.log_channel))

    async def format_initial_message(self, ctx):
        query = "SELECT * FROM logging WHERE guild_id=$1 AND channel_id=$2;"
        record = await ctx.bot.pool.fetchrow(query, ctx.guild.id, self.log_channel.id)
        if not record:
            content = f"No configuration exists for {self.log_channel.mention} yet!"
            # Disable certain buttons
            self.remove_logging_button.disabled = True
            self.change_format_button.disabled = True
        else:
            types = LoggingType(record['types'])
            if self.remove_logging_button.disabled is True:
                self.remove_logging_button.disabled = False
            if self.change_format_button.disabled is True:
                self.change_format_button.disabled = False
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
        await interaction.response.defer()
        await interaction.followup.send(f"Successfully set up logging for {self.log_channel.mention}! "
                                        f"({LoggingType.all.to_simple_str().replace('|', ', ')})")
        await self.update()

    @discord.ui.button(label="Setup specific logging events", style=discord.ButtonStyle.primary, emoji="\N{OPEN BOOK}")
    async def specific_events_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        async with self.sub_menu(view=SelectSubMenu(*[x.name for x in LoggingType.all],
                                 max_options=len(LoggingType.all))) as view:
            await interaction.response.defer()
            await interaction.edit_original_message(content='Select the events you wish to log', view=view)
            await view.wait()

            values = LoggingType.from_simple_str("|".join(view.values))
            query = """INSERT INTO logging (guild_id, channel_id, types)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (channel_id)
                       DO UPDATE SET types = EXCLUDED.types;"""
            await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id, int(values))
            await interaction.followup.send(f"Successfully set up logging for {self.log_channel.mention}! "
                                            f"({values.to_simple_str().replace('|', ', ')})")

    @discord.ui.button(label="Change logging format", style=discord.ButtonStyle.primary, emoji="\N{NOTEBOOK}")
    async def change_format_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        fmts = ['emoji', 'minimal with timestamp', 'minimal without timestamp', 'embed']
        async with self.sub_menu(view=SelectSubMenu(*fmts)) as view:
            await interaction.response.defer()
            await interaction.edit_original_message(content="Select the type of log format to change to", view=view)
            await view.wait()
            format_type = view.values[0].lower()
            connection = self.ctx.bot.pool
            query = """UPDATE logging SET format=$1 WHERE guild_id=$2 and channel_id=$3;"""
            await connection.execute(query, format_type, self.log_channel.guild.id,
                                     self.log_channel.id)

        await interaction.response.send_message(f"Successfully changed the log format to {format_type}!")
        self.invalidate()

    @discord.ui.button(label="Remove logging", style=discord.ButtonStyle.red, emoji="\N{CLOSED BOOK}")
    async def remove_logging_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        query = """DELETE FROM logging
                   WHERE guild_id=$1
                   AND channel_id=$2;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id)
        await interaction.response.defer()
        await interaction.followup.send(content=f"Removed logging from {self.log_channel.mention}!")
        self.invalidate()
        await self.update()
