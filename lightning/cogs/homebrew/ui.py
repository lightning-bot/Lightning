"""
Lightning.py - A Discord bot
Copyright (C) 2019-2023 LightSage

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
from discord.ext import menus

from lightning import ExitableMenu, UpdateableMenu, lock_when_pressed
from lightning.ui import MenuLikeView
from lightning.utils.paginator import Paginator


class _SelectSM(discord.ui.ChannelSelect['ChannelSelect']):
    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None

        await interaction.response.defer()

        self.view.stop(interaction=interaction)


class ChannelSelect(MenuLikeView):
    def __init__(self,
                 **kwargs):
        super().__init__(**kwargs)
        select = _SelectSM(max_values=1, channel_types=[discord.ChannelType.text],
                           placeholder="Select or type a channel in")
        self.add_item(select)

        self._select = select

    @property
    def values(self):
        return self._select.values or []

    async def cleanup(self, **kwargs) -> None:
        return


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
    @lock_when_pressed
    async def configure_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()

        content = "What channel would you like to use? You can select the channel below."
        view = ChannelSelect(context=self.ctx)
        m = await interaction.followup.send(content, view=view, wait=True)
        await view.wait()
        await m.delete()

        if not view.values:
            return

        channel = view.values[0].resolve()
        if not channel:
            channel = await view.values[0].fetch()

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
    async def remove_config_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
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


class UniversalDBPaginator(Paginator):
    source: menus.ListPageSource

    async def update_components(self) -> None:
        await super().update_components()

        entry = await self.source.get_page(self.current_page)
        prereleases = entry.get("prerelease", {})
        self.prereleases_button.disabled = not prereleases

    def format_downloads(self, entry):
        downloads = [f"[{k}]({v['url']})" for k, v in entry['downloads'].items()]
        return "\n".join(downloads)

    @discord.ui.button(label="Show pre-releases", row=2, style=discord.ButtonStyle.blurple)
    async def prereleases_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        entry = await self.source.get_page(self.current_page)
        embed = await self._get_page(self.current_page)
        embed.add_field(name="Latest Pre-releases", value=self.format_downloads(entry['prerelease']))
        await interaction.response.edit_message(embed=embed)
