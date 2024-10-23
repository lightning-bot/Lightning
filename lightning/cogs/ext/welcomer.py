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
from string import Template

import discord
from discord import app_commands

from lightning import GroupCog, LightningBot

TEMPLATING = """
**Variables**:

Guild Variables:
`$guild_name` - The server's name
`$guild_count` - The server's member count

Member Variables:
`$member` - The member's name#discrim
`$user` - An alias for `$member`
`$member_mention` - Mentions the member
"""

WHITELISTED_GUILDS = [1289261839804272712,  # DSi Mode Hacking!
                      540978015811928075,  # Test guild
                      283769550611152897]  # Archived DSI


def to_template(text, *, guild: discord.Guild, user: discord.Member):
    temp = Template(text)
    return temp.safe_substitute(guild_name=guild.name,
                                guild_count=guild.member_count,
                                member=str(user),
                                user=str(user),
                                member_mention=user.mention)


class LeaveMessageModal(discord.ui.Modal):
    def __init__(self, channel: discord.TextChannel) -> None:
        super().__init__(title="Set Leave Message")
        self.channel = channel

    message = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=2040)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = """INSERT INTO welcomer (guild_id, leave_message, leave_channel)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET
                    leave_message = EXCLUDED.leave_message,
                    leave_channel = EXCLUDED.leave_channel
                   """
        await interaction.client.pool.execute(query, interaction.guild.id, self.message.value, self.channel.id)

        example = to_template(self.message.value, guild=interaction.guild, user=interaction.user)
        await interaction.response.send_message(f"Set your leave message! Here's a preview:\n\n{example}")


class JoinMessageModal(discord.ui.Modal):
    def __init__(self, channel: discord.TextChannel) -> None:
        super().__init__(title="Set Join Message")
        self.channel = channel

    message = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=2040)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = """INSERT INTO welcomer (guild_id, join_message, join_channel)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET
                    join_message = EXCLUDED.join_message,
                    join_channel = EXCLUDED.join_channel
                   """
        await interaction.client.pool.execute(query, interaction.guild.id, self.message.value, self.channel.id)

        example = to_template(self.message.value, guild=interaction.guild, user=interaction.user)
        await interaction.response.send_message(f"Set your join message! Here's a preview:\n\n{example}")


@app_commands.default_permissions(manage_guild=True)
class Welcomer(GroupCog, group_name="welcomer"):
    """Welcomer commands for special servers"""
    def __init__(self, bot):
        super().__init__(bot)

    @app_commands.command(name="info")
    async def templating_info(self, interaction: discord.Interaction):
        """Tells you the variables for templating"""
        await interaction.response.send_message(TEMPLATING)

    @app_commands.command(name="set-leave-message")
    @app_commands.describe(channel="The channel to send leave messages to")
    async def set_leave_message(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the server's leave message"""
        modal = LeaveMessageModal(channel)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="set-join-message")
    @app_commands.describe(channel="The channel to send join messages to")
    async def set_join_message(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the server's join message"""
        modal = JoinMessageModal(channel)
        await interaction.response.send_modal(modal)

    async def get_guild_welcomer(self, guild_id: int):
        return await self.bot.pool.fetchrow("SELECT * FROM welcomer WHERE guild_id=$1;", guild_id)

    @GroupCog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id not in WHITELISTED_GUILDS:
            return

        record = await self.get_guild_welcomer(member.guild.id)
        if not record:
            return

        channel = member.guild.get_channel(record['leave_channel'])
        if not channel:
            return

        text = to_template(record['leave_message'], guild=member.guild, user=member)
        await channel.send(text, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=[member]))

    @GroupCog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id not in WHITELISTED_GUILDS:
            return

        record = await self.get_guild_welcomer(member.guild.id)
        if not record:
            return

        channel = member.guild.get_channel(record['join_channel'])
        if not channel:
            return

        text = to_template(record['join_message'], guild=member.guild, user=member)
        await channel.send(text, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=[member]))


async def setup(bot: LightningBot):
    await bot.add_cog(Welcomer(bot), guilds=[discord.Object(id=id) for id in WHITELISTED_GUILDS])
