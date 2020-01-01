# Lightning.py - A multi-purpose Discord bot
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

import discord
from discord.ext import commands
from utils import errors


def is_guild(guild_id):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id == guild_id:
            return True
        else:
            raise errors.LightningError("This command cannot be run in this server!")
    return commands.check(predicate)


def is_git_whitelisted(ctx):
    if not ctx.guild:
        return False
    guild = (ctx.guild.id in ctx.bot.config['git']['gitlab']['whitelisted_guilds'])
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
        if not ctx.guild:
            return False
        sr = await member_at_least_has_staff_role(ctx, ctx.author, min_role)
        if sr is True:
            return sr
        else:
            raise errors.MissingStaffRole(min_role)
    return commands.check(predicate)


def is_staff_or_has_perms(min_role: str, **perms):
    """
    Checks and verifies if a user has the needed staff level or permission
    """
    async def predicate(ctx):
        if not ctx.guild:
            return False
        permcheck = await check_guild_permissions(ctx, perms, check=all)
        sr = await member_at_least_has_staff_role(ctx, ctx.author, min_role)
        if sr is False and permcheck is False:
            permissions = []
            for permname in list(perms.keys()):
                permname = permname.replace('_', ' ').replace('guild', 'server').title()
                permissions.append(permname)
            raise errors.MissingRequiredPerms(permissions)
        return permcheck or sr
    return commands.check(predicate)


def has_channel_permissions(ctx, perms):
    """A copy of discord.py's has_permissions check
    https://github.com/Rapptz/discord.py/blob/d9a8ae9c78f5ca0eef5e1f033b4151ece4ed1028/discord/ext/commands/core.py#L1533
    """
    ch = ctx.channel
    permissions = ch.permissions_for(ctx.author)
    missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

    if missing is None:
        return True
    return False


def is_staff_or_has_channel_perms(min_role: str, **perms):
    """
    Checks and verifies if a user has the needed staff level or channel permission
    """
    async def predicate(ctx):
        if not ctx.guild:
            return False
        permissions = has_channel_permissions(ctx, perms)
        sr = await member_at_least_has_staff_role(ctx, ctx.author, min_role)
        if sr is False and permissions is False:
            permissions = []
            for permname in list(perms.keys()):
                permname = permname.replace('_', ' ').replace('guild', 'server').title()
                permissions.append(permname)
            raise errors.MissingRequiredPerms(permissions)
        return permissions or sr
    return commands.check(predicate)


async def check_guild_permissions(ctx, perms, *, check=all):
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner or ctx.author.id in ctx.bot.config['bot']['managers']:
        return True

    if not ctx.guild:
        return False

    resolved = ctx.author.guild_permissions
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


def has_guild_permissions(*, check=all, **perms):
    async def pred(ctx):
        permcheck = await check_guild_permissions(ctx, perms, check=check)
        if permcheck is False:
            permissions = []
            for permname in list(perms.keys()):
                permname = permname.replace('_', ' ').replace('guild', 'server').title()
                permissions.append(permname)
            raise errors.MissingRequiredPerms(permissions)
        return permcheck
    return commands.check(pred)


def is_bot_manager_or_staff(min_role: str):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        is_owner = await ctx.bot.is_owner(ctx.author)
        if is_owner:
            return True
        sr = await member_at_least_has_staff_role(ctx, ctx.author, min_role)
        if ctx.author.id in ctx.bot.config['bot']['managers']:
            return True
        return sr
    return commands.check(predicate)


async def is_bot_manager(ctx):
    """Check function to see if author is a bot manager or owner"""
    if not ctx.guild:
        return False
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True
    bm = ctx.author.id in ctx.bot.config['bot']['managers']
    if bm:
        return True
    raise errors.NotOwnerorBotManager


# A check function based off of Kirigiri.
# Under the AGPL v3 License,
# https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/LICENSE
async def member_at_least_has_staff_role(self, member: discord.Member,
                                         min_role: str = "Helper"):
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
