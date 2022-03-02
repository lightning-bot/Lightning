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
import asyncpg
import discord

from lightning import ExitableMenu, UpdateableMenu
from lightning.converters import SendableChannel


class NinUpdates(UpdateableMenu, ExitableMenu):
    async def fetch_record(self):
        query = "SELECT id FROM nin_updates WHERE guild_id=$1;"
        return await self.ctx.bot.pool.fetchval(query, self.ctx.guild.id)

    async def format_initial_message(self, ctx):
        # We're not using update_components method here since we also need to make a request for webhooks
        record = await self.fetch_record()
        if record is None:
            content = "Nintendo console updates are currently not configured!"
            self.configure_button.disabled = False
            self.remove_config_button.disabled = True
            return content

        webhook = discord.utils.get(await ctx.guild.webhooks(), id=record)
        if webhook is None:
            query = 'DELETE FROM nin_updates WHERE guild_id=$1'
            await self.ctx.bot.pool.execute(query, ctx.guild.id)
            # Disable remove config button since we already removed it
            self.remove_config_button.disabled = True
            content = "The webhook that sent Nintendo console update notifications seems to "\
                      "be deleted. Please re-configure by pressing the configure button."
            return content

        content = f"**Configuration**:\n\nDispatching messages to {webhook.channel.mention}"
        self.configure_button.disabled = True  # it's already configured
        self.remove_config_button.disabled = False
        return content

    @discord.ui.button(label="Configure", style=discord.ButtonStyle.primary)
    async def configure_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        content = "What channel would you like to use? You can send the ID, name, or mention of a channel."
        channel = await self.prompt_convert(interaction, content, SendableChannel())

        if not channel:
            return

        try:
            webhook = await channel.create_webhook(name="Nintendo Console Updates")
        except discord.HTTPException as e:
            await interaction.followup.send(f"Failed to create webhook. `{e}`", ephemeral=True)
            return

        query = """INSERT INTO nin_updates (guild_id, id, webhook_token)
                   VALUES ($1, $2, $3);"""
        try:
            await self.ctx.bot.pool.execute(query, self.ctx.guild.id, webhook.id, webhook.token)
        except asyncpg.UniqueViolationError:
            await interaction.followup.send("This server has already configured Nintendo console updates!",
                                            ephemeral=True)

        await self.update()

    @discord.ui.button(label="Remove configuration", style=discord.ButtonStyle.red)
    async def remove_config_button(self, button: discord.ui.Button, interaction: discord.Interaction) -> None:
        record = await self.ctx.bot.pool.fetchrow("SELECT * FROM nin_updates WHERE guild_id=$1", self.ctx.guild.id)
        if record is None:
            await interaction.response.send_message("Nintendo console updates are currently not configured!")
            return

        webhook = discord.utils.get(await self.ctx.guild.webhooks(), id=record['id'])
        query = "DELETE FROM nin_updates WHERE guild_id=$1;"

        if webhook is None:
            await self.ctx.bot.pool.execute(query, self.ctx.guild.id)
            await interaction.response.send_message("Successfully deleted configuration!")
        else:
            await webhook.delete()
            await self.ctx.bot.pool.execute(query, self.ctx.guild.id)
            await interaction.response.send_message("Successfully deleted webhook and configuration!")

        await self.update()
