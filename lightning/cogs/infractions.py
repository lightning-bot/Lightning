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

from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Literal, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands, menus
from sanctum.exceptions import NotFound

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       group, hybrid_command)
from lightning.converters import TargetMember
from lightning.enums import ActionType
from lightning.errors import LightningCommandError
from lightning.formatters import truncate_text
from lightning.utils.checks import has_guild_permissions
from lightning.utils.helpers import ticker
from lightning.utils.modlogformats import base_user_format
from lightning.utils.paginator import Paginator
from lightning.utils.time import add_tzinfo, natural_timedelta


class InfractionRecord:
    def __init__(self, bot: LightningBot, record: dict):
        self.id = record['id']

        self.guild = bot.get_guild(record['guild_id']) or record['guild_id']
        self.user = bot.get_user(record['user_id']) or record['user_id']
        self.moderator = bot.get_user(record['moderator_id']) or record['user_id']

        self.action = ActionType(record['action'])
        self.reason = record['reason']
        self.created_at = datetime.fromisoformat(record['created_at'])
        self.active = record['active']
        self.extra = record['extra']

    @property
    def guild_id(self):
        return self.guild.id if hasattr(self.guild, 'id') else self.guild

    @property
    def user_id(self):
        return self.user.id if hasattr(self.user, 'id') else self.user


class InfractionPaginator(Paginator):
    def __init__(self, source: menus.PageSource, context: GuildContext, /, *, timeout: Optional[float] = 90):
        super().__init__(source, context=context, timeout=timeout)
        self.bot = context.bot


class EphemeralInfractionPaginator(InfractionPaginator):
    async def format_initial_message(self, ctx):
        await self.source._prepare_once()
        page = await self._get_page(self.current_page)
        kwargs = self._assume_message_kwargs(page)
        kwargs['ephemeral'] = True
        return kwargs


class InfractionSource(menus.ListPageSource):
    def __init__(self, entries, *, member: Union[discord.User, discord.Member] = None):
        super().__init__(entries, per_page=5)
        self.member = member

    async def format_member_page(self, menu: InfractionPaginator, entries):
        embed = discord.Embed(color=discord.Color.dark_gray(), title=f"Infractions for {self.member}")
        for entry in entries:
            moderator = menu.bot.get_user(entry['moderator_id']) or entry['moderator_id']
            reason = entry['reason'] or 'No reason provided.'
            embed.add_field(name=f"{entry['id']}: {natural_timedelta(datetime.fromisoformat(entry['created_at']))}",
                            value=f"**Moderator**: {base_user_format(moderator)}\n"
                                  f"**Reason**: {truncate_text(reason, 45)}", inline=False)
        return embed

    async def format_all_page(self, menu: InfractionPaginator, entries):
        embed = discord.Embed(color=discord.Color.dark_gray())
        for entry in entries:
            user = menu.bot.get_user(entry['user_id']) or entry['user_id']
            mod = menu.bot.get_user(entry['moderator_id']) or entry['moderator_id']
            reason = entry['reason'] or 'No reason provided.'
            embed.add_field(name=f"{entry['id']}: {natural_timedelta(datetime.fromisoformat(entry['created_at']))}",
                            value=f"**User**: {base_user_format(user)}\n**Moderator**: {base_user_format(mod)}"
                                  f"\n**Reason**: {truncate_text(reason, 45)}",
                            inline=False)
        return embed

    async def format_page(self, menu: InfractionPaginator, entries):
        if self.member:
            return await self.format_member_page(menu, entries)
        else:
            return await self.format_all_page(menu, entries)


class InfractionFilterFlags(commands.FlagConverter):
    member: discord.Member
    active: bool = commands.flag(default=True)
    moderator: Optional[discord.Member]
    type: Optional[Literal['WARN', 'KICK', 'BAN', 'TEMPBAN', 'TEMPMUTE', 'MUTE']]


class Infractions(LightningCog, required=['Moderation']):
    """Infraction related commands"""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self.inf_list_contextmenu = app_commands.ContextMenu(name="View Infractions", callback=self.infraction_list)
        bot.tree.add_command(self.inf_list_contextmenu)

    async def cog_check(self, ctx) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @hybrid_command(name="mywarns", level=CommandLevel.User)
    @app_commands.guild_only()
    async def my_warns(self, ctx: GuildContext):
        """Shows your warnings in this server"""
        try:
            # type: ignore
            records: List[Dict[str, Any]] = await self.bot.api.get_user_infractions(ctx.guild.id, ctx.author.id)
        except NotFound:
            await ctx.send("No warnings found! Good for you!", ephemeral=True)
            return

        for record in records:
            if record['action'] != 1:
                records.remove(record)

        menu = EphemeralInfractionPaginator(InfractionSource(records, member=ctx.author), ctx, timeout=60.0)
        await menu.start(wait=False)

    # Context menu
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(kick_members=True)
    async def infraction_list(self, interaction: discord.Interaction, member: discord.Member):
        try:
            records = await self.bot.api.get_user_infractions(interaction.guild.id, member.id)
        except NotFound:
            await interaction.response.send_message(f"No infractions found for {member.mention}!", ephemeral=True)
            return

        ctx = await GuildContext.from_interaction(interaction)
        menu = EphemeralInfractionPaginator(InfractionSource(records, member=member), ctx, timeout=60.0)
        await menu.start(wait=False)

    @group(aliases=['inf'], invoke_without_command=True, level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def infraction(self, ctx: GuildContext) -> None:
        await ctx.send_help("infraction")

    @infraction.command(level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def view(self, ctx: GuildContext, infraction_id: int) -> None:
        """Views an infraction"""
        try:
            record = await self.bot.api.get_infraction(ctx.guild.id, infraction_id)
        except NotFound:
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
            return

        record = InfractionRecord(self.bot, record)
        embed = discord.Embed(title=str(record.action).capitalize(), description=record.reason or "No reason provided",
                              timestamp=add_tzinfo(record.created_at))
        embed.add_field(name="User", value=base_user_format(record.user))
        embed.add_field(name="Moderator", value=base_user_format(record.moderator))
        embed.add_field(name="Active", value=ticker(record.active), inline=False)
        embed.set_footer(text="Infraction created at")
        await ctx.send(embed=embed)

    @infraction.command(level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def claim(self, ctx: GuildContext, infraction_id: int) -> None:
        """Claims responsibility for an infraction"""
        try:
            await self.bot.api.edit_infraction(ctx.guild.id, infraction_id, {"moderator_id": ctx.author.id})
        except NotFound:
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
            return

        await ctx.send(f"Claimed {infraction_id}")

    @infraction.command(level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def edit(self, ctx: GuildContext, infraction_id: int, *, reason: str) -> None:
        """Edits the reason for an infraction"""
        try:
            await self.bot.api.edit_infraction(ctx.guild.id, infraction_id,
                                               {"moderator_id": ctx.author.id, "reason": reason})
        except NotFound:
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
            return

        await ctx.send(f"Edited {infraction_id}")

    @infraction.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def transfer(self, ctx: GuildContext, old_user: TargetMember, new_user: TargetMember) -> None:
        """Transfers a user's infractions to another user"""
        confirm = await ctx.confirm(f"Are you sure you want to transfer infractions from {old_user} to {new_user}?")
        if not confirm:
            return

        query = """UPDATE infractions SET user_id=$1 WHERE guild_id=$2 AND user_id=$3;"""
        resp = await self.bot.pool.execute(query, new_user.id, ctx.guild.id, old_user.id)
        resp = resp.split()

        await ctx.send(f"Transferred {resp[-1]} infractions to {new_user.mention}")

    @infraction.command(aliases=['remove'], level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def delete(self, ctx: GuildContext, infraction_id: int) -> None:
        """Deletes an infraction"""
        try:
            await self.bot.api.get_infraction(ctx.guild.id, infraction_id)
        except NotFound:
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
            return

        confirmation = await ctx.confirm(f"Are you sure you want to delete {infraction_id}? "
                                         "**This infraction cannot be restored once deleted!**")
        if not confirmation:
            return

        # I guess there could be instances where two people are running the same command...
        try:
            await self.bot.api.delete_infraction(ctx.guild.id, infraction_id)
        except NotFound:
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
            return

        await ctx.reply("Infraction deleted!")

    @infraction.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    @commands.bot_has_permissions(attach_files=True)
    async def export(self, ctx: GuildContext) -> None:
        """Exports the server's infractions to a JSON"""
        records = await self.bot.api.get_infractions(ctx.guild.id)

        raw_bytes = StringIO(records)
        raw_bytes.seek(0)
        await ctx.send(file=discord.File(raw_bytes, filename="infractions.json"))

    async def start_infraction_pages(self, ctx: GuildContext, source: InfractionSource) -> None:
        menu = InfractionPaginator(source, ctx, timeout=60.0)
        await menu.start(wait=False)

    async def wrap_request(self, coro):
        try:
            return await coro
        except NotFound:
            raise LightningCommandError("Couldn't find any infractions matching your criteria!")

    @infraction.command(name='list', invoke_without_command=True, level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def list_infractions(self, ctx: GuildContext, member: Optional[discord.User]) -> None:
        """Lists infractions that were done in the server with optional filter(s)"""
        if member:
            infs = await self.wrap_request(self.bot.api.get_user_infractions(ctx.guild.id, member.id))
            src = InfractionSource(infs, member=member)
        else:
            infs = await self.wrap_request(self.bot.api.get_infractions(ctx.guild.id))
            src = InfractionSource(infs)

        await self.start_infraction_pages(ctx, src)


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(Infractions(bot))
