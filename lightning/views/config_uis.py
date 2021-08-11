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

from lightning import ExitableMenu, LoggingType
from lightning.events import ChannelConfigInvalidateEvent


class LoggingTypeSelects(discord.ui.Select):
    def __init__(self):
        super().__init__(max_values=len(LoggingType.all),
                         options=[discord.SelectOption(label=x.name) for x in LoggingType.all])

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        ctx = self.view.ctx
        values = LoggingType.from_simple_str("|".join(self.values))
        query = """INSERT INTO logging (guild_id, channel_id, types)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (channel_id)
                   DO UPDATE SET types = EXCLUDED.types;"""
        await ctx.bot.pool.execute(query, ctx.guild.id, self.view.log_channel.id, int(values))
        self.view.invalidate()
        await interaction.response.send_message(f"Successfully set up logging for {self.view.log_channel.mention}! "
                                                f"({values.to_simple_str().replace('|', ' ')})")
        self.view.stop()


class LogFormatSelect(discord.ui.Select):
    def __init__(self):
        fmts = ['emoji', 'minimal with timestamp', 'minimal without timestamp', 'embed']
        super().__init__(max_values=1, options=[discord.SelectOption(label=x) for x in fmts])

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        format_type = self.values[0].lower()
        connection = self.view.ctx.bot.pool
        query = """UPDATE logging SET format=$1 WHERE guild_id=$2 and channel_id=$3;"""
        resp = await connection.execute(query, format_type, self.view.log_channel.guild.id,
                                        self.view.log_channel.id)

        if resp == "UPDATE 0":
            await interaction.response.send_message(f"{self.view.log_channel.mention} is not setup as a logging "
                                                    "channel!")
            self.view.stop()
            return

        await interaction.response.send_message(f"Successfully changed the log format to {format_type}!")
        self.view.invalidate()
        self.view.stop()


class Logging(ExitableMenu):
    def __init__(self, log_channel: discord.TextChannel, **kwargs):
        super().__init__(**kwargs)
        self.log_channel = log_channel

    def invalidate(self):
        self.ctx.bot.dispatch("lightning_channel_config_remove",
                              ChannelConfigInvalidateEvent(self.log_channel))

    def format_initial_message(self, ctx):
        return "Welcome to the interactive logging configuration setup, please select a button below to continue."

    @discord.ui.button(label="Log all events", style=discord.ButtonStyle.primary, emoji="\N{LEDGER}")
    async def log_all_events_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        query = """INSERT INTO logging (guild_id, channel_id, types)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (channel_id)
                   DO UPDATE SET types = EXCLUDED.types;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id, int(LoggingType.all))
        self.invalidate()
        await interaction.response.send_message(f"Successfully set up logging for {self.log_channel.mention}! "
                                                f"({LoggingType.all.to_simple_str().replace('|', ', ')})")
        self.stop()

    @discord.ui.button(label="Setup specific logging events", style=discord.ButtonStyle.primary, emoji="\N{OPEN BOOK}")
    async def specific_events_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        self.clear_items()
        self.add_item(LoggingTypeSelects())
        self.add_item(discord.ui.Button(label="Documentation",
                                        url="https://lightning-bot.gitlab.io/bot-configuration/#events"))
        await interaction.response.edit_message(content='Select the events you wish to log', view=self)

    @discord.ui.button(label="Change logging format", style=discord.ButtonStyle.primary, emoji="\N{NOTEBOOK}")
    async def change_format_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        self.clear_items()
        self.add_item(LogFormatSelect())
        await interaction.response.edit_message(content="Select the type of log format to change to", view=self)

    @discord.ui.button(label="View Configuration")
    async def view_config(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        query = "SELECT * FROM logging WHERE guild_id=$1 AND channel_id=$2;"
        record = await self.ctx.bot.pool.fetchrow(query, self.ctx.guild.id, self.log_channel.id)
        if not record:
            await interaction.response.edit_message(content="No configuration exists for this channel yet!")
        else:
            types = LoggingType(record['types'])
            await interaction.response.edit_message(content=f"Configuration for {self.log_channel.mention}:\n\n"
                                                            f"Events: {types.to_simple_str().replace('|', ', ')}\n"
                                                            f"Log Format: {record['format'].title()}")
        self.stop()

    @discord.ui.button(label="Remove logging", style=discord.ButtonStyle.red, emoji="\N{CLOSED BOOK}")
    async def remove_logging_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        query = """DELETE FROM logging
                   WHERE guild_id=$1
                   AND channel_id=$2;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id)

        await interaction.response.send_message(f"Removed logging from {self.log_channel.mention}!")
        self.invalidate()
