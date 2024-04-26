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
import discord

from lightning import (ExitableMenu, LoggingType, SelectSubMenu,
                       UpdateableMenu, lock_when_pressed)
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
    async def log_all_events_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        query = """INSERT INTO logging (guild_id, channel_id, types)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (channel_id)
                   DO UPDATE SET types = EXCLUDED.types;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id, -1)
        self.invalidate()
        await self.update(interaction=interaction)

    @discord.ui.button(label="Setup specific logging events", style=discord.ButtonStyle.primary, emoji="\N{OPEN BOOK}")
    async def specific_events_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.lock(interaction=interaction):
            view = SelectSubMenu(*[x.name for x in LoggingType.all], max_options=len(LoggingType.all), context=self.ctx)
            view.add_item(discord.ui.Button(label="Documentation",
                                            url="https://lightning.lightsage.dev/guide/modlog#events"))
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
