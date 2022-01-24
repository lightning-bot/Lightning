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
import re
from io import StringIO
from json import dumps as json_dumps

import discord
from discord.ext import menus
from discord.ext.commands import bot_has_permissions, default

from lightning import (CommandLevel, LightningBot, LightningCog,
                       LightningContext, group)
from lightning.converters import TargetMember
from lightning.errors import LightningError
from lightning.formatters import truncate_text
from lightning.utils.checks import has_guild_permissions
from lightning.utils.helpers import ticker
from lightning.utils.modlogformats import ActionType, base_user_format
from lightning.utils.time import add_tzinfo, natural_timedelta


class InfractionRecord:
    def __init__(self, bot: LightningBot, record: dict):
        self.id = record['id']

        self.guild = bot.get_guild(record['guild_id']) or record['guild_id']
        self.user = bot.get_user(record['user_id']) or record['user_id']
        self.moderator = bot.get_user(record['moderator_id']) or record['user_id']

        self.action = ActionType(record['action'])
        self.reason = record['reason']
        self.created_at = record['created_at']
        self.active = record['active']
        self.extra = record['extra']

    @property
    def guild_id(self):
        return self.guild.id if hasattr(self.guild, 'id') else self.guild

    @property
    def user_id(self):
        return self.user.id if hasattr(self.user, 'id') else self.user


class InfractionSource(menus.KeysetPageSource):
    def __init__(self, bot, guild, *, member=None, moderator=None, **kwargs):
        self.guild = guild
        self.bot = bot
        self.connection = bot.pool

        self.member = member
        self.moderator = moderator
        self._has_ran = False
        super().__init__(**kwargs)

    def is_paginating(self):
        return True

    async def get_page(self, specifier):
        query = """SELECT * FROM
                       (SELECT * FROM infractions {where_clause} ORDER BY created_at {sort} LIMIT 5)
                   subq ORDER BY created_at;"""

        args = []
        if specifier.reference is None:
            where_clause = 'WHERE guild_id=$1'
            args.append(self.guild.id)
        elif specifier.direction is menus.PageDirection.after:
            where_clause = 'WHERE id > $1 AND guild_id=$2'
            args.append(specifier.reference[-1]['id'])
            args.append(self.guild.id)
        else:  # PageDirection.before
            where_clause = 'WHERE id < $1 AND guild_id=$2'
            args.append(specifier.reference[0]['id'])
            args.append(self.guild.id)

        if self.member:
            last_arg = int(re.findall(r"\$\d+", where_clause)[-1].strip("$"))
            where_clause += f' AND user_id=${last_arg + 1}'
            args.append(self.member.id)

        if self.moderator:
            last_arg = int(re.findall(r"\$\d+", where_clause)[-1].strip("$"))
            where_clause += f' AND moderator_id=${last_arg + 1}'
            args.append(self.moderator.id)

        sort = 'ASC' if specifier.direction is menus.PageDirection.after else 'DESC'

        records = await self.connection.fetch(query.format(where_clause=where_clause, sort=sort), *args)

        if self._has_ran is False and not records:
            raise LightningError("No infractions matched your critiera")

        if self._has_ran is False:
            self._has_ran = True

        if not records:
            raise ValueError

        return records

    def format_embed_description(self, embed: discord.Embed, entries: list) -> discord.Embed:
        if self.member:
            for entry in entries:
                moderator = self.bot.get_user(entry['moderator_id']) or entry['moderator_id']
                reason = entry['reason'] or 'No reason provided.'
                embed.add_field(name=f"{entry['id']}: {natural_timedelta(entry['created_at'])}",
                                value=f"**Moderator**: {base_user_format(moderator)}\n"
                                      f"**Reason**: {truncate_text(reason, 45)}", inline=False)
        elif self.moderator:
            for entry in entries:
                user = self.bot.get_user(entry['user_id']) or entry['user_id']
                reason = entry['reason'] or 'No reason provided.'
                embed.add_field(name=f"{entry['id']}: {natural_timedelta(entry['created_at'])}",
                                value=f"**User**: {base_user_format(user)}\n"
                                      f"**Reason**: {truncate_text(reason, 45)}", inline=False)
        else:
            for entry in entries:
                user = self.bot.get_user(entry['user_id']) or entry['user_id']
                mod = self.bot.get_user(entry['moderator_id']) or entry['moderator_id']
                reason = entry['reason'] or 'No reason provided.'
                embed.add_field(name=f"{entry['id']}: {natural_timedelta(entry['created_at'])}",
                                value=f"**User**: {base_user_format(user)}\n**Moderator**: {base_user_format(mod)}"
                                      f"\n**Reason**: {truncate_text(reason, 45)}",
                                inline=False)
        return embed

    async def format_page(self, menu, entries):
        embed = self.format_embed_description(discord.Embed(), entries)

        if self.member:
            embed.title = f"Infractions for {str(self.member)}"
        elif self.moderator:
            embed.title = f"Infractions made by {str(self.moderator)}"
        else:
            embed.title = "Server-wide infractions"

        embed.color = discord.Color.dark_grey()

        return embed


def serialize_infraction(record) -> dict:
    data = dict(record)

    data['created_at'] = record['created_at'].isoformat()
    data['expiry'] = record['expiry'].isoformat() if record['expiry'] else None

    return data


class Infractions(LightningCog, required=['Mod']):
    """Infraction related commands"""

    @group(aliases=['inf'], invoke_without_command=True, level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def infraction(self, ctx: LightningContext) -> None:
        await ctx.send_help("infraction")

    @infraction.command(level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def view(self, ctx: LightningContext, infraction_id: int) -> None:
        """Views an infraction"""
        query = """SELECT * FROM infractions WHERE id=$1 AND guild_id=$2;"""
        record = await self.bot.pool.fetchrow(query, infraction_id, ctx.guild.id)
        if not record:
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
    async def claim(self, ctx: LightningContext, infraction_id: int) -> None:
        """Claims responsibility for an infraction"""
        query = """UPDATE infractions
                   SET moderator_id=$1
                   WHERE guild_id=$2 AND id=$3;"""
        resp = await self.bot.pool.execute(query, ctx.author.id, ctx.guild.id, infraction_id)

        if resp == "UPDATE 0":
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
            return

        await ctx.send(f"Claimed {infraction_id}")

    @infraction.command(level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def edit(self, ctx: LightningContext, infraction_id: int, *, reason: str) -> None:
        """Edits the reason for an infraction"""
        query = """UPDATE infractions
                   SET moderator_id=$1, reason=$2
                   WHERE guild_id=$3 AND id=$4;"""
        resp = await self.bot.pool.execute(query, ctx.author.id, reason, ctx.guild.id, infraction_id)

        if resp == "UPDATE 0":
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
            return

        await ctx.send(f"Edited {infraction_id}")

    @infraction.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    async def transfer(self, ctx: LightningContext, old_user: TargetMember, new_user: TargetMember) -> None:
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
    async def delete(self, ctx: LightningContext, infraction_id: int) -> None:
        """Deletes an infraction"""
        # TODO: Query table before
        confirmation = await ctx.confirm(f"Are you sure you want to delete {infraction_id}? "
                                         "**This infraction cannot be restored once deleted!**")
        if not confirmation:
            return

        query = """DELETE FROM infractions
                   WHERE id=$1
                   AND guild_id=$2;"""
        resp = await self.bot.pool.execute(query, infraction_id, ctx.guild.id)
        if resp == "DELETE 0":
            await ctx.send(f"An infraction with ID {infraction_id} does not exist.")
        else:
            await ctx.send("Infraction deleted!")

    @infraction.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_guild=True)
    @bot_has_permissions(attach_files=True)
    async def export(self, ctx: LightningContext) -> None:
        """Exports the server's infractions to a JSON"""
        records = await self.bot.pool.fetch("SELECT * FROM infractions WHERE guild_id=$1;", ctx.guild.id)

        raw_bytes = StringIO(json_dumps(list(map(serialize_infraction, records))))
        raw_bytes.seek(0)
        await ctx.send(file=discord.File(raw_bytes, filename="infractions.json"))

    async def start_keyset_pages(self, ctx: LightningContext, source: InfractionSource) -> None:
        menu = menus.MenuKeysetPages(source, timeout=60.0, clear_reactions_after=True,
                                     check_embeds=True)
        await menu.start(ctx)

    @infraction.group(name='list', invoke_without_command=True, level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def list_infractions(self, ctx: LightningContext) -> None:
        """Lists infractions for the server"""
        await self.start_keyset_pages(ctx, InfractionSource(ctx.bot, ctx.guild))

    @list_infractions.command(name='member', level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def list_infractions_member(self, ctx: LightningContext, *, member: discord.User) -> None:
        """Lists infractions done to a user"""
        await self.start_keyset_pages(ctx, InfractionSource(ctx.bot, ctx.guild, member=member))

    @list_infractions.command(name='takenby', level=CommandLevel.Mod)
    @has_guild_permissions(manage_guild=True)
    async def list_infractions_made_by(self, ctx: LightningContext, *,
                                       member: discord.Member = default.Author) -> None:
        """Lists infractions taken by a moderator"""
        await self.start_keyset_pages(ctx, InfractionSource(ctx.bot, ctx.guild, moderator=member))


def setup(bot: LightningBot) -> None:
    bot.add_cog(Infractions(bot))
