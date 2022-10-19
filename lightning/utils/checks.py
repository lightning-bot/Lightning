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
import discord
from discord.ext import commands

from lightning import errors


def is_guild(guild_id):
    def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id == guild_id:
            return True
        else:
            raise errors.LightningError("This command cannot be run in this server!")
    return commands.check(predicate)


def is_one_of_guilds(*guilds):
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.guild.id in guilds:
            return True
    return commands.check(predicate)


def check_channel_permissions(ctx, perms):
    """A copy of discord.py's has_permissions check
    https://github.com/Rapptz/discord.py/blob/d9a8ae9c78f5ca0eef5e1f033b4151ece4ed1028/discord/ext/commands/core.py#L1533
    """
    ch = ctx.channel
    permissions = ch.permissions_for(ctx.author)
    missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

    if not missing:
        return True
    raise commands.MissingPermissions(missing)


def has_channel_permissions(**permissions):
    async def predicate(ctx):
        return check_channel_permissions(ctx, permissions)
    predicate.channel_permissions = list(permissions.keys())
    return commands.check(predicate)


async def check_guild_permissions(ctx, perms, *, check=all):
    if await ctx.bot.is_owner(ctx.author):
        return True

    if not ctx.guild:
        return False

    resolved = ctx.author.guild_permissions
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


def has_guild_permissions(**permissions):
    async def pred(ctx):
        permcheck = await check_guild_permissions(ctx, permissions, check=all)
        if permcheck is False:
            raise commands.MissingPermissions(list(permissions.keys()))
        return permcheck
    # Note to myself: Change these to __lightning_user_guild_requires__ when rewriting.
    pred.guild_permissions = list(permissions.keys())
    return commands.check(pred)


def no_threads():
    """Disallows a command to be ran in a thread channel"""
    def predicate(ctx):
        if isinstance(ctx.channel, discord.Thread):
            raise errors.NoThreadChannels()

        return True
    return commands.check(predicate)
