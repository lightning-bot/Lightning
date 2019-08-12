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
from database import Roles

class ToggleRoles(commands.Cog):
    """Role Cog"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')

        
    @commands.guild_only()
    @commands.command(aliases=['gettoggleableroles', 'list_toggleable_roles'])
    @commands.bot_has_permissions(embed_links=True)
    async def get_toggleable_roles(self, ctx):
        """Lists all the toggleable roles this guild has"""
        session = self.bot.dbsession()
        embed = discord.Embed(title="Toggleable Role List", color=discord.Color.dark_purple())
        role_list = []
        for row in session.query(Roles).filter_by(guild_id=ctx.guild.id):
            role = discord.utils.get(ctx.guild.roles, id=row.role_id)
            embed.description = ""
            role_list.append(role)
            for s in role_list:
                embed.description += f"{s.mention} | Role ID {s.id}\n"
        embed.set_footer(text=f"{ctx.guild.name}")
        session.close()
        await ctx.send(embed=embed)

    
    @commands.guild_only()
    @commands.command(aliases=['roleme'], pass_context=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def togglerole(self, ctx, *, role: discord.Role):
        """Toggle a role that this server has setup.
        Use '.get_toggleable_roles' for a list of roles that you can toggle."""
        session = self.bot.dbsession()
        roles_db = Roles
        add = session.query(roles_db).filter_by(role_id=role.id).all()
        member = ctx.author
        if role in member.roles:
            return await ctx.send("You already have that role.")

        if add:
            await member.add_roles(role, reason="Toggled Role")
            session.close()
            return await ctx.send(f"{member.mention} now has the role **{role.name}** 🎉")
        else:
            session.close()
            return await ctx.send("That role is not toggleable.")

    @commands.guild_only()
    @commands.command(aliases=['unroleme'], pass_context=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def untogglerole(self, ctx, *, role: discord.Role):
        """Untoggle a role that this server has setup.
        Use '.get_toggleable_roles' for a list of roles that you can untoggle."""
        session = self.bot.dbsession()
        roles_db = Roles
        add = session.query(roles_db).filter_by(role_id=role.id).all()
        member = ctx.author

        if role in member.roles and add:
            await member.remove_roles(role, reason="Untoggled Role")
            session.close()
            return await ctx.send(f"{member.mention} You have untoggled the role **{role.name}**")
        elif role not in member.roles and add:
            session.close()
            return await ctx.send(f"You do not have {role.name}.")
        else:
            session.close()
            return await ctx.send("That role is not toggleable.")


def setup(bot):
    bot.add_cog(ToggleRoles(bot))
