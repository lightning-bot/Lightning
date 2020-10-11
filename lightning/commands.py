"""
Lightning.py - A multi-purpose Discord bot
Copyright (C) 2020 - LightSage

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

__all__ = ('CommandLevel', 'command', 'group', 'LightningCommand', 'LightningGroupCommand')


class CommandLevel(discord.Enum):
    User = 1
    Trusted = 2
    Mod = 3
    Admin = 4
    Owner = 5
    Blocked = 6


def command(**kwargs):
    def inner(func):
        cls = kwargs.get('cls', LightningCommand)
        return cls(func, **kwargs)
    return inner


def group(**kwargs):
    def inner(func):
        cls = kwargs.get('cls', LightningGroupCommand)
        return cls(func, **kwargs)
    return inner


class LightningCommand(commands.Command):
    def __init__(self, func, **kwargs):
        super().__init__(func, **kwargs)
        level = kwargs.pop('level', CommandLevel.User)
        if not isinstance(level, CommandLevel):
            raise TypeError("level kwarg must be an instance of CommandLevel")
        self.level = level

    async def _check_level(self, ctx) -> bool:
        # We need to check custom overrides first...
        bot = ctx.bot
        overrides = await bot.get_command_overrides(ctx.guild.id)
        if overrides is not None:
            ids = [r.id for r in ctx.author.roles]
            ids.append(ctx.author.id)
            if overrides.is_command_id_overriden(self.qualified_name, ids) is True:
                return True

            if overrides.is_command_level_blocked(self.qualified_name) is True:
                return False

        # Now the regular permissions
        perm = await bot.get_permissions_config(ctx.guild.id)

        if perm is None:
            # We're gonna assume they are a user unless otherwise
            user_level = CommandLevel.User
        else:
            user_level = perm.get_user_level(ctx.author.id, [r.id for r in ctx.author.roles])

        if user_level == CommandLevel.Blocked and self.level == CommandLevel.Blocked:
            return True

        if user_level == CommandLevel.Blocked and self.level != user_level:
            return False

        if user_level.value >= self.level.value:
            return True

        should_fallback = getattr(perm, 'fallback_to_discord_perms', True)
        if not should_fallback:
            return False

        predicates = [pred for pred in self.checks if hasattr(pred, 'guild_permissions') or hasattr(pred, 'channel_permissions')]  # noqa
        if not predicates:
            # No permissions to fallback to...
            return False

        return await discord.utils.async_all(pred(ctx) for pred in predicates)

    async def can_run(self, ctx):
        await super().can_run(ctx)
        return await self._check_level(ctx)


class LightningGroupCommand(LightningCommand, commands.Group):
    pass
