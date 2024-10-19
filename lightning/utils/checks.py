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
import discord
from discord import app_commands
from discord.ext import commands

from lightning import LightningBot, errors
from lightning.commands import CommandLevel


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
    """A command check to allow a command to be used in one of specified guilds"""
    async def predicate(ctx) -> bool:
        if not ctx.guild:
            return False

        if ctx.guild.id in guilds:
            return True

        return False
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

    predicate.guild_permissions = list(permissions.keys())
    return commands.check(predicate)


def hybrid_guild_permissions(**permissions: bool):
    async def predicate(ctx):
        if ctx.interaction is not None:
            return True

        if await ctx.bot.is_owner(ctx.author):
            return True

        f = commands.has_guild_permissions(**permissions)
        return await f.predicate(ctx)

    def deco(func):
        predicate.guild_permissions = list(permissions.keys())
        commands.check(predicate)(func)
        app_commands.default_permissions(**permissions)(func)
        return func

    return deco


def is_server_manager():
    """A shortcut for hybrid_guild_permissions with Manage Guild as True"""
    return hybrid_guild_permissions(manage_guild=True)


def no_threads():
    """Disallows a command to be ran in a thread channel"""
    def predicate(ctx):
        if isinstance(ctx.channel, discord.Thread):
            raise errors.NoThreadChannels()

        return True
    return commands.check(predicate)


async def get_member_level(bot: LightningBot, author: discord.Member) -> CommandLevel:
    cfg = await bot.get_guild_bot_config(author.guild.id)
    if not cfg or not cfg.permissions or not cfg.permissions.levels:
        return CommandLevel.User

    return cfg.permissions.levels.get_user_level(author.id, [i.id for i in author.roles])


async def has_required_level(level: CommandLevel, **permissions: bool):
    """Checks if the invoking user has permissions to use the app command"""
    async def predicate(interaction: discord.Interaction):
        # We'll prioritize discord guild permissions...
        try:
            return app_commands.checks.has_permissions(**permissions).predicate(interaction)
        except app_commands.CheckFailure:
            pass

        user = await get_member_level(interaction.client, interaction.user)  # type: ignore
        return user.value >= level.value
    return app_commands.check(predicate)

# These are dangerous permissions, self assignable roles are meant to only give roles with basic permissions.
# i.e. send_messages, read_message_history
# This is used for permission checking when adding a new role to the list or toggling one.
# I don't think anyone has used the bot yet to raid communities, but this is a safeguard for the future.
DANGEROUS_PERMISSIONS = discord.Permissions(manage_threads=True, ban_members=True, manage_roles=True,
                                            manage_guild=True, manage_messages=True, manage_channels=True,
                                            administrator=True, kick_members=True, deafen_members=True,
                                            manage_webhooks=True, manage_nicknames=True, mention_everyone=True,
                                            move_members=True, moderate_members=True, manage_expressions=True)


def has_dangerous_permissions(permissions: discord.Permissions):
    """Returns True/False if the object has permissions that are deemed dangerous"""
    return permissions.value & DANGEROUS_PERMISSIONS.value != 0


def is_premium_guild():
    async def predicate(ctx):
        if ctx.guild is None:
            raise commands.CommandError("This command can only be used in premium guilds!")
        return False
    return commands.check(predicate)
