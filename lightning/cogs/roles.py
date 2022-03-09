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
import typing
from io import StringIO

import discord
import tabulate
from discord.ext import commands
from discord.ext.commands.view import StringView
from rapidfuzz import process

from lightning import (CommandLevel, LightningBot, LightningCog,
                       LightningContext, command, group)
from lightning.converters import Role
from lightning.utils import paginator
from lightning.utils.checks import has_guild_permissions


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


# These are dangerous permissions, self assignable roles are meant to only give roles with basic permissions.
# i.e. send_messages, read_message_history
# This is used for permission checking when adding a new role to the list or toggling one.
# I don't think anyone has used the bot yet to raid communities, but this is a safeguard for the future.
DANGEROUS_PERMISSIONS = discord.Permissions(manage_threads=True, ban_members=True, manage_roles=True,
                                            manage_guild=True, manage_messages=True, manage_channels=True,
                                            administrator=True, kick_members=True, deafen_members=True,
                                            manage_webhooks=True, manage_nicknames=True, mention_everyone=True,
                                            move_members=True, moderate_members=True)


class Roles(LightningCog):
    """Role based commands"""

    @command()
    @commands.guild_only()
    async def rolemembers(self, ctx: LightningContext, *, role: discord.Role) -> None:
        """Lists members that have a certain role"""
        if len(role.members) == 0:
            await ctx.send(f"{str(role)} has no members.")
            return

        fp = StringIO(tabulate.tabulate([(str(r), r.id) for r in role.members], ("Name", "ID")))
        await ctx.send(file=discord.File(fp, "members.txt"))

    async def resolve_roles(self, record, ctx, args):
        roles = []
        for x in record:
            role = ctx.guild.get_role(x)
            if role:
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

    def _has_dangerous_permissions(self, permissions: discord.Permissions):
        if permissions.value & DANGEROUS_PERMISSIONS.value != 0:
            # has dangerous permissions
            return True
        return False

    @group(aliases=['selfrole'], invoke_without_command=True, require_var_positional=True)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    async def togglerole(self, ctx: LightningContext, *roles) -> None:
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
            check = self._has_dangerous_permissions(role.permissions)
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

    @togglerole.command(name="add", aliases=["set"], level=CommandLevel.Admin)
    @commands.guild_only()
    @has_guild_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def set_toggleable_roles(self, ctx, *, role: Role) -> None:
        """Adds a role to the list of toggleable roles for members"""
        query = """INSERT INTO guild_config (guild_id, toggleroles)
                   VALUES ($1, $2::bigint[])
                   ON CONFLICT (guild_id)
                   DO UPDATE SET toggleroles =
                   ARRAY(SELECT DISTINCT * FROM unnest(COALESCE(guild_config.toggleroles, '{}') || $2::bigint[]))
                """
        await self.bot.pool.execute(query, ctx.guild.id, [role.id])
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.send(f"Added {role.name} as a toggleable role!")

    @togglerole.command(name="purge", level=CommandLevel.Admin)
    @commands.guild_only()
    @has_guild_permissions(manage_roles=True)
    async def purge_toggleable_roles(self, ctx: LightningContext) -> None:
        """Deletes all the toggleable roles you have set in this server"""
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
    async def remove_toggleable_role(self, ctx: LightningContext, *, role: typing.Union[discord.Role, int]) -> None:
        """Removes a role from the toggleable role list"""
        role_repr = (role.id if hasattr(role, 'id') else role, role.name if hasattr(role, 'name') else role)
        await self.remove_assignable_role(ctx.guild.id, role_repr[0])
        await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)
        await ctx.send(f"Successfully removed {role_repr[1]} from the list of toggleable roles")

    @commands.guild_only()
    @togglerole.command(name="list")
    async def list_toggleable_roles(self, ctx: LightningContext) -> None:
        """Lists all the self-assignable roles this server has"""
        record = await self.bot.get_guild_bot_config(ctx.guild.id)
        if not record or not record.toggleroles:
            await ctx.send("This feature is not setup in this server.")
            return

        # Unresolved roles shouldn't generally need to be handled as it's handled in the listener below
        # but it's kept as a just-in-case the bot is down when a role is deleted.
        unresolved = []
        role_list = []

        for role_id in record.toggleroles:
            role = discord.utils.get(ctx.guild.roles, id=role_id)
            if role:
                role_list.append(f"{role.mention} (ID: {role.id})")
            else:
                unresolved.append(role_id)

        if len(unresolved) != 0:
            # We have some roles that need to be removed...
            query = """UPDATE guild_config
                       SET toggleroles = ARRAY(SELECT x FROM unnest(toggleroles) AS x
                             WHERE NOT(x = ANY($1::bigint[])))
                       WHERE guild_id=$2;"""
            await self.bot.pool.execute(query, unresolved, ctx.guild.id)
            await self.bot.get_guild_bot_config.invalidate(ctx.guild.id)

        embed = discord.Embed(title="Self-Assignable Roles", color=discord.Color.greyple())
        menu = paginator.InfoMenuPages(paginator.BasicEmbedMenu(role_list, per_page=12, embed=embed),
                                       clear_reactions_after=True, check_embeds=True)
        await menu.start(ctx)

    @LightningCog.listener()
    async def on_lightning_guild_role_delete(self, event):
        await self.remove_assignable_role(event.guild_id, event.role.id)
        await self.bot.get_guild_bot_config.invalidate(event.guild_id)


def setup(bot: LightningBot):
    bot.add_cog(Roles(bot))
