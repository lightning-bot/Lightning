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

from io import StringIO
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

import discord
import tabulate
from discord import app_commands
from discord.ext import commands
from discord.ext.commands.view import StringView
from rapidfuzz import process

from lightning import (CommandLevel, GuildContext, LightningCog, command,
                       group, hybrid_command)
from lightning.cogs.roles.menus import PersistedRolesSource, RoleSource
from lightning.cogs.roles.ui import RoleButton, RoleButtonView
from lightning.converters import Role
from lightning.events import GuildRoleDeleteEvent
from lightning.utils import paginator
from lightning.utils.checks import (has_dangerous_permissions,
                                    has_guild_permissions,
                                    hybrid_guild_permissions)

if TYPE_CHECKING:
    from lightning.cogs.mod import Mod as ModCog


class RoleView(StringView):
    def get_word(self):
        current = self.current
        if current is None:
            return None

        result = [current.strip(",")]

        while not self.eof:
            current = self.get()
            if not current:
                return ''.join(result)

            if current == ",":
                return ''.join(result)

            result.append(current)


class Roles(LightningCog):
    """Role based commands"""
    async def cog_load(self):
        self.bot.loop.create_task(self.init_existing_togglerole_buttons())

    @command()
    @commands.guild_only()
    async def rolemembers(self, ctx: GuildContext, *, role: discord.Role) -> None:
        """Lists members that have a certain role"""
        if len(role.members) == 0:
            await ctx.send(f"{str(role)} has no members.")
            return

        fp = StringIO(tabulate.tabulate([(str(r), r.id) for r in role.members], ("Name", "ID")))
        await ctx.send(file=discord.File(fp, "members.txt"))

    async def resolve_roles(self, record, ctx, args) -> Tuple[List[discord.Role], List[str]]:
        roles = []
        for x in record:
            if role := ctx.guild.get_role(x):
                roles.append(role)
            continue
        role_names = [r.name for r in roles]

        view = RoleView(' '.join(args))
        args = []
        while not view.eof:
            word = view.get_word()
            if word is None:
                break
            args.append(word.strip())

        resolved = []
        unresolved = []
        for argument in args:
            try:
                role = await commands.RoleConverter().convert(ctx, argument)
            except commands.BadArgument:
                name = process.extractOne(argument, role_names, score_cutoff=75)
                if name is None:
                    unresolved.append(argument)
                    continue

                role = discord.utils.get(roles, name=name[0])

                if not role:
                    unresolved.append(argument)
                    continue
            resolved.append(role)
        return resolved, unresolved

    @group(invoke_without_command=True, require_var_positional=True)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    async def togglerole(self, ctx: GuildContext, *roles) -> None:
        """Toggles a role that this server has setup.

        To toggle multiple roles, you'll need to use a comma (",") as a separator.

        Use "{prefix}togglerole list" for a list of roles that you can toggle."""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record or not record.toggleroles:
            await ctx.send("This feature is not setup in this server.")
            return

        resolved, unresolved = await self.resolve_roles(record.toggleroles, ctx, roles)

        member = ctx.author
        diff_roles = ([], [])

        paginator = commands.Paginator(prefix='', suffix='')
        for role in resolved:
            check = has_dangerous_permissions(role.permissions)
            if check is True:
                paginator.add_line(f"Refusing to give {role.name} because it contains permissions that are deemed"
                                   " dangerous")
                continue

            if role.is_assignable() is False:
                paginator.add_line(f"Unable to assign {role.name}")
                continue

            if role in member.roles and role.id in record.toggleroles:
                diff_roles[0].append(role)
                paginator.add_line(f"Removed role **{role.name}**")
            elif role not in member.roles and role.id in record.toggleroles:
                diff_roles[1].append(role)
                paginator.add_line(f"Added role **{role.name}**")
            else:
                paginator.add_line(f"**{role.name}** is not toggleable!")

        if diff_roles[0]:
            await member.remove_roles(*diff_roles[0], reason="User untoggled role")

        if diff_roles[1]:
            await member.add_roles(*diff_roles[1], reason="User toggled role")

        for r in unresolved:
            paginator.add_line(f"Unable to resolve \"{r}\"")

        for page in paginator.pages:
            await ctx.send(page)

    @togglerole.command(name="add", level=CommandLevel.Admin)
    @commands.guild_only()
    @has_guild_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def set_toggleable_roles(self, ctx: GuildContext, *,
                                   role: discord.Role = commands.param(converter=Role)) -> None:
        """Adds a role to the list of toggleable roles for members"""
        if has_dangerous_permissions(role.permissions):
            await ctx.send(f"Unable to add {role.name} ({role.id}) because it has permissions that are deemed "
                           "dangerous.")
            return

        query = """INSERT INTO guild_config (guild_id, toggleroles)
                   VALUES ($1, $2::bigint[])
                   ON CONFLICT (guild_id)
                   DO UPDATE SET toggleroles =
                   ARRAY(SELECT DISTINCT * FROM unnest(COALESCE(guild_config.toggleroles, '{}') || $2::bigint[]))
                """
        await self.bot.pool.execute(query, ctx.guild.id, [role.id])
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.send(f"Added {role.name} as a toggleable role!")
        self.bot.loop.create_task(self.update_togglerole_buttons(ctx.guild))

    @togglerole.command(name="purge", level=CommandLevel.Admin)
    @commands.guild_only()
    @has_guild_permissions(manage_roles=True)
    async def purge_toggleable_roles(self, ctx: GuildContext) -> None:
        """Deletes all the toggleable roles you have set in this server"""
        confirm = await ctx.confirm("Are you sure you want to remove all the self-assignable roles?")
        if not confirm:
            return

        query = """UPDATE guild_config
                   SET toggleroles=NULL
                   WHERE guild_id=$1;"""
        resp = await self.bot.pool.execute(query, ctx.guild.id)

        if resp == "UPDATE 0":
            await ctx.send("This server had no toggleable roles")
        else:
            await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
            await ctx.send("All toggleable roles have been deleted.")

    async def remove_assignable_role(self, guild_id, role_id):
        query = """UPDATE guild_config
                   SET toggleroles = array_remove(toggleroles, $1)
                   WHERE guild_id=$2;
                 """
        await self.bot.pool.execute(query, role_id, guild_id)

    @togglerole.command(name="delete", aliases=['remove'], level=CommandLevel.Admin)
    @commands.guild_only()
    @has_guild_permissions(manage_roles=True)
    async def remove_toggleable_role(self, ctx: GuildContext, *, role: Union[discord.Role, int]) -> None:
        """Removes a role from the toggleable role list"""
        role_repr = (role.id if hasattr(role, 'id') else role, role.name if hasattr(role, 'name') else role)
        await self.remove_assignable_role(ctx.guild.id, role_repr[0])
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.send(f"Successfully removed {role_repr[1]} from the list of toggleable roles")
        self.bot.loop.create_task(self.update_togglerole_buttons(ctx.guild))

    async def start_role_pages(self, ctx, roles: List[discord.Role]):
        pages = paginator.Paginator(RoleSource(roles, per_page=12), context=ctx)
        await pages.start(wait=False)

    @commands.guild_only()
    @togglerole.command(name="list")
    async def list_toggleable_roles(self, ctx: GuildContext) -> None:
        """Lists all the self-assignable roles this server has"""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record or not record.toggleroles:
            await ctx.send("This feature is not setup in this server.")
            return

        # Unresolved roles shouldn't generally need to be handled as it's handled in the listener below
        # but it's kept as a just-in-case the bot is down when a role is deleted.
        unresolved = []
        roles = []

        for role_id in record.toggleroles:
            if role := discord.utils.get(ctx.guild.roles, id=role_id):
                roles.append(role)
            else:
                unresolved.append(role_id)

        if unresolved:
            # We have some roles that need to be removed...
            query = """UPDATE guild_config
                       SET toggleroles = ARRAY(SELECT x FROM unnest(toggleroles) AS x
                             WHERE NOT(x = ANY($1::bigint[])))
                       WHERE guild_id=$2;"""
            await self.bot.pool.execute(query, unresolved, ctx.guild.id)
            await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)

        await self.start_role_pages(ctx, roles)

    @LightningCog.listener()
    async def on_lightning_guild_role_delete(self, event: GuildRoleDeleteEvent):
        await self.remove_assignable_role(event.guild_id, event.role.id)
        await self.bot.get_guild_bot_config.invalidate(event.guild_id)

    # Some things to note:
    # - This implementation only allows for either one message with 25 buttons or a channel designed for buttons only
    # - An ID PK column would make this implmentation support other messages.
    async def init_existing_togglerole_buttons(self):
        await self.bot.wait_until_ready()

        records = await self.bot.pool.fetch("SELECT * FROM togglerole_interactions")
        for record in records:
            guild = self.bot.get_guild(record['guild_id'])
            if not guild:
                return

            if record['message_id']:
                view = await self._prepare_view(guild, record['channel_id'])
                self.bot.add_view(view, message_id=record['message_id'])

    async def update_togglerole_buttons(self, guild: discord.Guild):
        record = await self.bot.pool.fetchrow("SELECT * FROM togglerole_interactions WHERE guild_id=$1;", guild.id)
        if not record:
            return

        channel = guild.get_channel(record['channel_id'])
        if not channel:  # sus
            return

        message = await channel.fetch_message(record['message_id'])
        view = await self._prepare_view(guild, channel.id)
        await message.edit(view=view)

    async def simple_button_view(self, ctx: GuildContext):
        message = await ctx.ask("What would you like the message content to be?")
        if not message:
            return

        view = await self._prepare_view(ctx.guild, ctx.channel.id)
        message = await ctx.send(message.content, view=view)
        query = """INSERT INTO togglerole_interactions (guild_id, channel_id, message_id)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET channel_id = EXCLUDED.channel_id,
                   message_id = EXCLUDED.message_id"""
        await self.bot.pool.execute(query, ctx.guild.id, message.channel.id, message.id)
        await ctx.send("Bound to this message! Any time you delete or add a self-assignable role, that change will be "
                       "reflected in this menu.", reference=message)

    @togglerole.command(level=CommandLevel.Admin)
    @has_guild_permissions(manage_roles=True)
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def buttons(self, ctx: GuildContext):
        """Sets up role buttons"""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record or not record.toggleroles:
            await ctx.send("This feature cannot be used until you add some roles!")
            return

        if len(record.toggleroles) <= 25:
            await self.simple_button_view(ctx)
            return

        await ctx.send(f"This command only works if the guild has less than {len(record.toggleroles)} self-assignable "
                       "roles.")

    async def _prepare_view(self, guild: discord.Guild, channel_id: int) -> RoleButtonView:
        view = RoleButtonView()
        config = await self.bot.get_guild_bot_config(guild.id)
        roles = sorted(guild.get_role(role) for role in config.toggleroles)  # hopefully nothing is None...
        for role in roles:
            view.add_item(RoleButton(role, channel_id))
        return view

    # Slash commands
    @app_commands.command(name='togglerole')
    @app_commands.describe(role="The role to assign")
    @app_commands.guild_only()
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def togglerole_slash(self, interaction: discord.Interaction, role: discord.Role) -> None:
        """Adds/removes a self-assignable role to you"""
        record = await self.bot.get_guild_bot_config(interaction.guild.id)
        if not record or not record.toggleroles:
            await interaction.response.send_message("This feature is not setup in this server.", ephemeral=True)
            return

        if role.id not in record.toggleroles:
            # We'll list off the roles that are toggleable...
            await interaction.response.send_message("This role is not toggleable.", ephemeral=True)
            return

        if has_dangerous_permissions(role.permissions):
            await interaction.response.send_message("This role has permissions that are deemed dangerous!",
                                                    ephemeral=True)
            return

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("This role is too high for me to assign to you!", ephemeral=True)
            return

        if interaction.user._roles.has(role.id):
            await interaction.user.remove_roles(role, reason="togglerole slash command usage")
            await interaction.response.send_message(f"Removed {role.name}!", ephemeral=True)
        else:
            await interaction.user.add_roles(role, reason="togglerole slash command usage")
            await interaction.response.send_message(f"Added {role.name}!", ephemeral=True)

    # Role state
    @hybrid_command(name="persistrole", aliases=['persist'], level=CommandLevel.Admin)
    @hybrid_guild_permissions(manage_roles=True)
    @app_commands.describe(member="The member to persist a role to", role="The role to persist")
    async def persist_role(self, ctx: GuildContext, member: discord.Member, role: discord.Role):
        """Assigns a role to a member that will always be reapplied"""
        if role >= ctx.guild.me.top_role:
            await ctx.send("This role is too high for me to assign to you!", ephemeral=True)
            return

        if has_dangerous_permissions(role.permissions):
            await ctx.send("This role has permissions that are deemed dangerous", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason="Role Persistance")
        except discord.Forbidden:
            await ctx.send(f"I was unable to add the role to {member.mention}", ephemeral=True)
            return

        cog: Optional[ModCog] = self.bot.get_cog("Moderation")  # type: ignore
        if not cog:
            await ctx.send("This feature is unavailable right now!", ephemeral=True)
            return

        await cog.add_punishment_role(ctx.guild.id, member.id, role.id)

        await ctx.send(f"Persisted {role.name} to {member.mention}!", ephemeral=True)

    @hybrid_command(level=CommandLevel.Mod)
    @hybrid_guild_permissions(manage_roles=True)
    async def persisted(self, ctx: GuildContext):
        """
        Lists all members with persisted roles

        Do note, if you use a mute role, those will also show up here.
        """
        query = """SELECT guild_id, user_id, punishment_roles
                   FROM roles
                   WHERE guild_id=$1
                   AND array_length(punishment_roles, 1) > 0;"""
        records = await self.bot.pool.fetch(query, ctx.guild.id)
        if not records:
            await ctx.send("Nobody has any persisted roles!", ephemeral=True)
            return

        pages = paginator.Paginator(PersistedRolesSource(records, per_page=5), context=ctx)
        await pages.start(wait=False, ephemeral=True)

    @hybrid_command(aliases=['rmpersist'], level=CommandLevel.Admin)
    @hybrid_guild_permissions(manage_roles=True)
    @app_commands.describe(member="The member to remove a role from", role="The role to remove")
    async def unpersist(self, ctx: GuildContext, member: discord.Member, role: discord.Role):
        """Removes a role that's been persisted to a member"""
        if role >= ctx.guild.me.top_role:
            await ctx.send(f"This role is too high for me to remove from {str(member)}!", ephemeral=True)
            return

        if has_dangerous_permissions(role.permissions):
            await ctx.send("This role has permissions that are deemed dangerous", ephemeral=True)
            return

        cog: Optional[ModCog] = self.bot.get_cog("Moderation")  # type: ignore
        if not cog:
            await ctx.send("This feature is unavailable right now!", ephemeral=True)
            return

        role_check = await cog.punishment_role_check(ctx.guild.id, member.id, role.id)
        if not role_check:
            await ctx.send("I cannot remove a role that has not been persisted before!", ephemeral=True)
            return

        try:
            await member.remove_roles(role, reason="Removing Role Persistance")
        except discord.Forbidden:
            await ctx.send(f"I was unable to remove the role from {member.mention}", ephemeral=True)
            return

        await cog.remove_punishment_role(ctx.guild.id, member.id, role.id)
        await ctx.send(f"Removed the role from {member.mention} and removed persistance!", ephemeral=True)
