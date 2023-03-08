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
    async def predicate(ctx) -> bool:
        return ctx.guild.id in guilds if ctx.guild else False

    return commands.check(predicate)


def has_channel_permissions(**permissions):
    c = commands.has_permissions(**permissions)

    async def predicate(ctx):
        return await c.predicate(ctx)

    predicate.channel_permissions = list(permissions.keys())
    return commands.check(predicate)


def has_guild_permissions(**permissions):
    check = commands.has_guild_permissions(**permissions)

    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True

        return await check.predicate(ctx)
    # Note to myself: Change these to __lightning_user_guild_requires__ when rewriting.
    predicate.guild_permissions = list(permissions.keys())
    return commands.check(predicate)


def no_threads():
    """Disallows a command to be ran in a thread channel"""
    def predicate(ctx):
        if isinstance(ctx.channel, discord.Thread):
            raise errors.NoThreadChannels()

        return True
    return commands.check(predicate)
