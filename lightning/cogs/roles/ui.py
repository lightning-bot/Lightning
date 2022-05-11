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
from __future__ import annotations

import discord

from lightning import BaseView


class RoleButtonView(BaseView):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return isinstance(interaction.user, discord.Member)


class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role, channel_id: int, **kwargs):
        self.role_id = role.id
        super().__init__(style=discord.ButtonStyle.primary, label=role.name,
                         custom_id=f"lightning-tgbutton-{channel_id}-{role.id}", **kwargs)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("I don't have the `Manage Roles` permission!", ephemeral=True)
            return

        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("I couldn't find the role associated with this button.",
                                                    ephemeral=True)
            return

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("This role is too high for me to assign to you!", ephemeral=True)
            return

        if interaction.user._roles.has(self.role_id):
            await interaction.user.remove_roles(role, reason="Role button usage")
            await interaction.response.send_message(f"Removed {role.name}!", ephemeral=True)
        else:
            await interaction.user.add_roles(role, reason="Role button usage")
            await interaction.response.send_message(f"Added {role.name}!", ephemeral=True)
