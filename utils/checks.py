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
import config

def is_guild(guild_id):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id == guild_id:
            return True
    return commands.check(predicate)

def is_git_whitelisted(ctx):
    if not ctx.guild:
        return False
    guild = (ctx.guild.id in config.gh_whitelisted_guilds)
    return (guild)

def is_one_of_guilds(guilds: list):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id in guilds:
            return True
    return commands.check(predicate)

def has_staff_role(min_role: str):
    """
        Checks and verifies if a user has the needed staff level

        min_role is either admin, mod or helper.

        Quick overview of what to grant to whom (permissions are incremental):
        - Helper: User nicknames, warnings.
        - Moderator: Kicking and banning users.
        - Admin: Server management.
    """
    async def predicate(ctx):
        sr = await member_at_least_has_staff_role(ctx, ctx.author, min_role)
        return sr
    return commands.check(predicate)

def is_staff_or_has_perms(min_role: str, **perms):
    """
    Checks and verifies if a user has the needed staff level or permission
    """
    async def predicate(ctx):
        sr = await member_at_least_has_staff_role(ctx, ctx.author, min_role)
        if sr:
            return True
        permissions = ctx.author.guild_permissions
        return all(getattr(permissions, perms, None) == value for perms, value in perms.items())
    return commands.check(predicate)

def is_bot_manager_or_staff(min_role: str):
    async def predicate(ctx):
        sr = await member_at_least_has_staff_role(ctx, ctx.author, min_role)
        if ctx.author.id in config.bot_managers:
            return True
        owner = await ctx.bot.is_owner(ctx.author)
        return any(sr or owner)
    return commands.check(predicate)

def is_bot_manager(ctx):
    """Check function to see if author is a bot manager or owner"""
    async def predicate(ctx):
        if not ctx.guild:
            return False
        owner = await ctx.bot.is_owner(ctx.author)
        if owner:
            return True
        if ctx.author.id in config.bot_managers:
            return True
    return commands.check(predicate)
        

# A check function based off of Kirigiri.
# Under the AGPL v3 License, 
# https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/LICENSE
async def member_at_least_has_staff_role(self, member: discord.Member, min_role: str="Helper"):
    """
    Non-check function for check_if_at_least_has_staff_role()
    """
    if not hasattr(member, 'roles'):
        return False
    role_list = ["helper", "moderator", "admin"]
    for role in role_list.copy():
        if role_list.index(role) < role_list.index(min_role.lower()):
            role_list.remove(role)

    query = """SELECT role_id FROM staff_roles
               WHERE guild_id=$1
               AND perms=$2;
            """
    staff_roles = []
    for role in role_list:
        async with self.bot.db.acquire() as con:
            out = await con.fetch(query, member.guild.id, role)
        for role_id in out:
            staff_roles.append(role_id)
    user_roles = [role.id for role in member.roles]
    if len(staff_roles) == 0:
        return False
    tmp = [r[0] for r in staff_roles]
    if any(role in user_roles for role in tmp):
        return True
    else:
        return False