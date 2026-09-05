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
import discord

from lightning import LoggingType, SelectSubMenu, UpdateableLayoutView
from lightning.cogs.modlog.utils import human_friendly_log_names
from lightning.constants import LIGHTNING_COLOR
from lightning.events import ChannelConfigInvalidateEvent

LOGGING_FORMATS = [
    discord.SelectOption(label='Emoji', value='emoji',
                         description='Text logs with an emoji for each event.'),
    discord.SelectOption(label='Minimal with Timestamp', value='minimal with timestamp',
                         description='Simple text logs with the event time.'),
    discord.SelectOption(label='Minimal without Timestamp', value='minimal without timestamp',
                         description='Simple text logs without a timestamp.'),
    discord.SelectOption(label='Embed', value='embed',
                         description='Logs displayed in a structured embed.'),
]


class EventsRow(discord.ui.ActionRow):
    view: 'LoggingCV2'

    @discord.ui.button(label="Log all events", style=discord.ButtonStyle.primary, emoji="\N{LEDGER}")
    async def log_all_events_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.view.save_events(-1)
        await self.view.update(interaction=interaction)

    @discord.ui.button(label="Choose events", style=discord.ButtonStyle.primary, emoji="\N{OPEN BOOK}")
    async def specific_events_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async with self.view.lock(interaction=interaction):
            await interaction.response.defer(ephemeral=True)
            record = await self.view.fetch_record()
            selected = LoggingType(record['types']) if record else LoggingType(0)
            options = [discord.SelectOption(label=human_friendly_log_names(event), value=event.name,
                                            default=event in selected)
                       for event in LoggingType.all]
            view = SelectSubMenu(*options, max_options=len(options), context=self.view.ctx)
            view.add_item(discord.ui.Button(label="Documentation",
                                            url="https://lightning.lightsage.dev/guide/modlog#events"))
            msg = await interaction.followup.send(
                content="Choose the events to log in this channel. Submitting saves your selection immediately.",
                view=view, wait=True, ephemeral=True)
            await view.wait()

            if view.values:
                values = LoggingType.from_simple_str("|".join(view.values))
                await self.view.save_events(int(values))
            await msg.delete()


class RemoveLoggingButton(discord.ui.Button):
    view: 'LoggingCV2'

    def __init__(self) -> None:
        super().__init__(label="Remove logging", style=discord.ButtonStyle.red, emoji="\N{CLOSED BOOK}")

    async def callback(self, interaction: discord.Interaction) -> None:
        query = """DELETE FROM logging
                   WHERE guild_id=$1
                   AND channel_id=$2;"""
        await self.view.ctx.bot.pool.execute(query, self.view.ctx.guild.id, self.view.log_channel.id)
        self.view.invalidate()
        await self.view.update(interaction=interaction)


class ModLogFormatRow(discord.ui.ActionRow):
    view: 'LoggingCV2'

    @discord.ui.select(options=LOGGING_FORMATS, placeholder="Choose how logs should look")
    async def change_format_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        if not select.values:
            return

        query = """UPDATE logging SET format=$1 WHERE guild_id=$2 and channel_id=$3;"""
        await self.view.ctx.bot.pool.execute(query, select.values[0], self.view.ctx.guild.id,
                                             self.view.log_channel.id)
        self.view.invalidate()
        await self.view.update(interaction=interaction)


class LoggingCV2(UpdateableLayoutView):
    container = discord.ui.Container(accent_color=LIGHTNING_COLOR)

    def __init__(self, log_channel: discord.TextChannel, **kwargs) -> None:
        super().__init__(**kwargs, delete_message_after=False)
        self.log_channel = log_channel
        self.events_desc = discord.ui.TextDisplay("")
        self.format_desc = discord.ui.TextDisplay("")
        self.format_row = ModLogFormatRow()
        self.remove_button = RemoveLoggingButton()
        self.build_components()

    def invalidate(self) -> None:
        self.ctx.bot.dispatch("lightning_channel_config_remove",
                              ChannelConfigInvalidateEvent(self.log_channel))

    async def fetch_record(self):
        query = "SELECT * FROM logging WHERE guild_id=$1 AND channel_id=$2;"
        return await self.ctx.bot.pool.fetchrow(query, self.ctx.guild.id, self.log_channel.id)

    async def save_events(self, types: int) -> None:
        query = """INSERT INTO logging (guild_id, channel_id, types)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (channel_id)
                   DO UPDATE SET types = EXCLUDED.types;"""
        await self.ctx.bot.pool.execute(query, self.ctx.guild.id, self.log_channel.id, types)
        self.invalidate()

    def build_components(self) -> None:
        self.container.add_item(discord.ui.TextDisplay(
            f"## Moderation Logging · {self.log_channel.mention}\n"
            "-# Choose what gets logged here. Changes save immediately."))
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(self.events_desc)
        self.container.add_item(EventsRow())
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(self.format_desc)
        self.container.add_item(self.format_row)
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(discord.ui.TextDisplay(
            "### Stop logging here\n"
            "Remove this channel's logging settings to stop new logs. Existing messages will stay."))
        self.container.add_item(discord.ui.ActionRow(self.remove_button))

    async def update_components(self) -> None:
        record = await self.fetch_record()
        configured = record is not None
        events = "None selected yet"
        if configured:
            types = LoggingType(record['types'])
            if types == LoggingType.all:
                events = "All events"
            else:
                events = human_friendly_log_names(types) if types else "None selected"
        self.events_desc.content = (
            "### 1. What should Lightning log?\n"
            "Log all supported events, or choose only the ones your team needs.\n"
            f"**Currently: {events}**")
        current_format = record['format'] if configured else None
        self.format_desc.content = (
            "### 2. How should logs look?\n"
            "Choose a display style for new log messages.\n"
            + (f"**Currently: {current_format.title()}**" if configured else
               "Choose events first to unlock this setting."))
        self.remove_button.disabled = not configured
        self.format_row.change_format_select.disabled = not configured
        # Fresh options keep the selected format local to this view.
        self.format_row.change_format_select.options = [
            discord.SelectOption(label=option.label, value=option.value, description=option.description,
                                 default=option.value == current_format)
            for option in LOGGING_FORMATS
        ]
