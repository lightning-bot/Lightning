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

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from sanctum.exceptions import NotFound

from lightning import CommandLevel, GuildContext, LightningCog, hybrid_command
from lightning.cache import registry as cache_registry
from lightning.cogs.reports.ui import (ReasonModal, ReportConfiguration,
                                       ReportDashboard)
from lightning.models import GuildModConfig
from lightning.utils.checks import is_server_manager

if TYPE_CHECKING:
    from lightning.cogs.mod import Mod


# At some point this might be a premium feature...
class Reports(LightningCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.report_context_menu = app_commands.ContextMenu(name="Report Message", callback=self.report)
        self.bot.tree.add_command(self.report_context_menu)

    async def cog_load(self) -> None:
        self.bot.loop.create_task(self.start_all_views())

    async def cog_unload(self) -> None:
        await self.stop_all_running_views()
        self.bot.tree.remove_command(self.report_context_menu.name, type=self.report_context_menu.type)

    async def stop_all_running_views(self):
        for view in self.bot.persistent_views:
            if isinstance(view, ReportDashboard):
                view.stop()

    async def start_all_views(self):
        await self.bot.wait_until_ready()

        records = await self.bot.pool.fetch("SELECT * FROM message_reports;")
        for record in records:
            # Skip any reports that we can't manage...
            if not self.bot.get_guild(record['guild_id']):
                continue

            view = ReportDashboard.from_record(record)
            self.bot.add_view(view, message_id=record['report_message_id'])

    def get_mod_cog(self) -> Optional[Mod]:
        return self.bot.get_cog("Moderation")  # type: ignore

    async def get_message_report_config(self, guild_id: int) -> Optional[GuildModConfig]:
        cog = self.get_mod_cog()
        if not cog:
            return

        record = await cog.get_mod_config(guild_id)
        return record

    @LightningCog.listener()
    async def on_guild_channel_delete(self, channel: discord.TextChannel):
        record = await self.get_message_report_config(channel.guild.id)
        if not record or record.message_report_channel_id is None:
            return

        if channel.id != record.message_report_channel_id:
            return

        query = "UPDATE guild_mod_config SET message_report_channel_id=NULL WHERE guild_id=$1;"
        await self.bot.pool.execute(query, channel.guild.id)
        query = "DELETE FROM message_reports WHERE guild_id=$1;"
        await self.bot.pool.execute(query, channel.guild.id)

        if c := cache_registry.get("mod_config"):
            await c.invalidate(str(channel.guild.id))

        # Stop listening to views from that guild.
        for view in self.bot.persistent_views:
            if isinstance(view, ReportDashboard) and view.guild_id == channel.guild.id:
                view.stop()

    @LightningCog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        # Stop all views associated with that guild
        for view in self.bot.persistent_views:
            if isinstance(view, ReportDashboard) and view.guild_id == guild.id:
                view.stop()

    def message_info_embed(self, msg: discord.Message) -> discord.Embed:
        embed = discord.Embed(timestamp=msg.created_at)

        if hasattr(msg.author, 'nick') and msg.author.display_name != str(msg.author):
            author_name = f"{msg.author.display_name} ({msg.author})"
        else:
            author_name = msg.author

        embed.set_author(name=author_name, icon_url=msg.author.display_avatar.url)

        if msg.guild:
            embed.set_footer(text=f"\N{NUMBER SIGN}{msg.channel}")
        else:
            embed.set_footer(text=msg.channel)

        description = msg.content
        if msg.attachments:
            attach_urls = [
                f'[{attachment.filename}]({attachment.url})'
                for attachment in msg.attachments
            ]

            description += '\n\N{BULLET} ' + '\n\N{BULLET} '.join(attach_urls)
        if msg.embeds:
            description += "\n \N{BULLET} Message contains an embed(s)"
        embed.description = description

        if hasattr(msg.author, 'color'):
            embed.color = msg.author.color

        return embed

    async def create_new_report(self, interaction: discord.Interaction, message: discord.Message, *,
                                reason: Optional[str] = "No reason provided."):
        guild = message.guild

        record = await self.get_message_report_config(guild.id)
        if not record or record.get_message_report_channel() is None:
            return

        channel = record.get_message_report_channel()

        try:
            record = await self.bot.api.get_guild_message_report(guild.id, message.id)
        except NotFound:
            record = None

        if record:
            if record['dismissed'] is True:
                return

            await self.bot.api.add_guild_message_reporter(guild.id, message.id, {"author_id": interaction.user.id,
                                                                                 "reason": reason})
            return

        view = ReportDashboard(message.id, guild.id, message.channel.id)
        dash_msg = await channel.send("\N{POLICE CARS REVOLVING LIGHT} A new message was reported.\n"
                                      "Please see the embed below to see the contents of the message",
                                      embeds=[self.message_info_embed(message)],
                                      view=view)

        payload = {"guild_id": guild.id, "message_id": message.id, "channel_id": message.channel.id,
                   "report_message_id": dash_msg.id,
                   "reporter": {"author_id": interaction.user.id, "reason": reason, "original": True}}
        record = await self.bot.api.create_guild_message_report(guild.id, payload)

    @hybrid_command(name='reportsetup', level=CommandLevel.Admin)
    @is_server_manager()
    @app_commands.guild_only()
    async def report_setup(self, ctx: GuildContext):
        """Configure the message report feature"""
        view = ReportConfiguration(context=ctx, delete_message_after=True)
        await view.start(wait=False)

    @app_commands.guild_only()
    async def report(self, interaction: discord.Interaction, message: discord.Message):
        if message.author.bot:
            await interaction.response.send_message("You can't report messages from bots!", ephemeral=True)
            return

        cog = self.get_mod_cog()
        if not cog:
            await interaction.response.send_message("Unable to report messages at this time.", ephemeral=True)
            return

        record = await cog.get_mod_config(interaction.guild.id)
        if not record or record.message_report_channel_id is None:
            await interaction.response.send_message("Message reporting is not set up in this server!", ephemeral=True)
            return

        modal = ReasonModal()
        await interaction.response.send_modal(modal)
        await modal.wait()

        await self.create_new_report(interaction, message, reason=modal.reason.value)
        await interaction.followup.send("<a:wee:630185233227972618><a:woo:630185257248882718> Successfully reported!",
                                        ephemeral=True)
