# Lightning.py - The Successor to Lightning.js
# Copyright (C) 2019 - LightSage
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation at version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# In addition, clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version

import discord
from discord.ext import commands
from utils.paginators_jsk import paginator_embed
from utils.converters import RoleSearch
import asyncpg


class ToggleRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @commands.guild_only()
    @commands.group(aliases=['roleme'], invoke_without_command=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def togglerole(self, ctx, *, role: RoleSearch):
        """Toggles a role that this server has setup.

        Use '.togglerole list' for a list of roles that you can toggle."""
        query = """SELECT role_id FROM toggleable_roles WHERE guild_id=$1 AND role_id=$2"""
        res = await self.bot.db.fetchval(query, ctx.guild.id, role.id)

        member = ctx.author
        if role > ctx.me.top_role:
            return await ctx.send('That role is higher than my highest role.')
        if role in member.roles and res:
            await member.remove_roles(role, reason="Untoggled Role")
            return await ctx.safe_send(f"Untoggled role **{role.name}**")
        elif res:
            await member.add_roles(role, reason="Toggled Role")
            return await ctx.safe_send(f"Toggled role **{role.name}**")
        else:
            return await ctx.send("That role is not toggleable.")

    @commands.guild_only()
    @togglerole.command(name="add", aliases=["set"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def set_toggleable_roles(self, ctx, *, role: discord.Role):
        """Adds a role to the list of toggleable roles for members"""
        if role > ctx.author.top_role:
            return await ctx.send('That role is higher than your highest role.')
        if role > ctx.me.top_role:
            return await ctx.send('Role is higher than my highest role.')
        query = """INSERT INTO toggleable_roles (guild_id, role_id)
                   VALUES ($1, $2);
                """
        try:
            await self.bot.db.execute(query, ctx.guild.id, role.id)
        except asyncpg.UniqueViolationError:
            return await ctx.send("That role is already added as a toggleable role.")
        await ctx.safe_send(f"Added {role.name} as a toggleable role!")

    @commands.guild_only()
    @togglerole.command(name="purge")
    @commands.has_permissions(manage_roles=True)
    async def purge_toggleable_role(self, ctx):
        """Deletes all the toggleable roles you have set in this guild"""
        query = """DELETE FROM toggleable_roles WHERE guild_id=$1;"""
        async with self.bot.db.acquire() as con:
            await con.execute(query, ctx.guild.id)
        await ctx.send("All toggleable roles have been deleted.")

    @commands.guild_only()
    @togglerole.command(name="delete")
    @commands.has_permissions(manage_roles=True)
    async def rm_t_role(self, ctx, *, role: discord.Role):
        """Removes a role from the toggleable role list"""
        query = """DELETE FROM toggleable_roles
                   WHERE guild_id=$1
                   AND role_id=$2;
                """
        async with self.bot.db.acquire() as con:
            res = await con.execute(query, ctx.guild.id, role.id)
        if res == 'DELETE 0':
            return await ctx.safe_send(f"{role.name} was never set as a toggleable role!")
        await ctx.safe_send(f"Successfully removed {role.name} from the "
                            "list of toggleable roles")

    @commands.guild_only()
    @togglerole.command(name="list", aliases=['get'])
    async def get_toggleable_roles(self, ctx):
        """Lists all the toggleable roles this guild has"""
        embed = discord.Embed(title="Toggleable Role List", color=discord.Color.dark_purple())
        role_list = []
        query = """SELECT role_id FROM toggleable_roles WHERE guild_id=$1;
                """
        res = await self.bot.db.fetch(query, ctx.guild.id)
        if len(res) == 0:
            return await ctx.send("This guild does not have any toggleable roles.")
        for row in res:
            role = discord.utils.get(ctx.guild.roles, id=row[0])
            role_list.append(role)
        pages = []
        for s in role_list:
            pages.append(f"{s.mention} | Role ID {s.id}")
        await paginator_embed(self.bot, ctx, embed, size=1250, page_list=pages)


def setup(bot):
    bot.add_cog(ToggleRoles(bot))
