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
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Union

import discord
import yarl
from discord.ext import commands

from lightning.commands import CommandLevel
from lightning.context import GuildContext
from lightning.errors import (ChannelPermissionFailure, HierarchyException,
                              InvalidLevelArgument, LightningError)

if TYPE_CHECKING:
    from lightning import LightningContext

log = logging.getLogger(__name__)


class GuildorNonGuildUser(commands.Converter):
    async def convert(self, ctx: LightningContext, argument):
        try:
            target = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            target = await commands.UserConverter().convert(ctx, argument)
        return target


class TargetMember(commands.Converter):
    def __init__(self, *, fetch_user=True):
        if fetch_user:
            self.user_converter = GuildorNonGuildUser()
        else:
            self.user_converter = commands.MemberConverter()

    async def check_member(self, ctx: LightningContext, member: Union[discord.User, discord.Member]):
        if member.id == ctx.me.id:
            raise commands.BadArgument("Bots can't do actions on themselves.")

        if member.id == ctx.author.id:
            raise commands.BadArgument("You can't do actions on yourself.")

        if isinstance(member, discord.Member):
            if member.id == ctx.guild.owner_id:
                raise commands.BadArgument("You can't do actions on the server owner.")

            if member.top_role >= ctx.author.top_role:
                raise commands.BadArgument("You can't do actions on this member due to hierarchy.")

    async def convert(self, ctx: LightningContext, argument: str):
        target = await self.user_converter.convert(ctx, argument)
        await self.check_member(ctx, target)
        return target


class ReadableTextChannel(commands.Converter):
    async def convert(self, ctx, argument):
        channel = await commands.TextChannelConverter().convert(ctx, argument)
        if not channel.permissions_for(ctx.me).read_messages:
            raise ChannelPermissionFailure(f"I don't have permission to view channel {channel.mention}")
        if not ctx.author or not channel.permissions_for(ctx.author).read_messages:
            raise ChannelPermissionFailure(f"You don't have permission to view channel {channel.mention}")
        return channel


class ReadableThread(commands.Converter):
    async def convert(self, ctx, argument):
        thread = await commands.ThreadConverter().convert(ctx, argument)
        if not thread.permissions_for(ctx.me).read_messages:
            raise ChannelPermissionFailure(f"I don't have permission to view thread {thread.mention}")
        if not ctx.author or not thread.permissions_for(ctx.author).read_messages:
            raise ChannelPermissionFailure(f"You don't have permission to view channel {thread.mention}")
        return thread


class SendableChannel(commands.Converter):
    async def convert(self, ctx, argument):
        channel = await commands.TextChannelConverter().convert(ctx, argument)
        if not channel.permissions_for(ctx.me).send_messages:
            raise ChannelPermissionFailure("I don't have permission to send "
                                           f"messages in {channel.mention}")
        if not ctx.author or not channel.permissions_for(ctx.author).send_messages:
            raise ChannelPermissionFailure("You don't have permission to "
                                           f"send messages in {channel.mention}")
        return channel


class ValidCommandName(commands.Converter):
    async def convert(self, ctx, argument):
        lowered = argument.lower()

        valid_commands = {
            c.qualified_name
            for c in ctx.bot.walk_commands()
            if c.cog_name not in ('Configuration', 'Owner',
                                  'Jishaku', 'Git')
        }

        if lowered not in valid_commands:
            raise LightningError(f'Command {lowered!r} is not valid.')

        return lowered


class EmojiRE(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            emoji = await commands.EmojiConverter().convert(ctx, argument)
        except commands.EmojiNotFound:
            regexmatch = re.match(r"<(a?):([A-Za-z0-9_]+):([0-9]+)>", argument)
            if not regexmatch:
                raise commands.BadArgument("That's not a custom emoji \N{THINKING FACE}")
            try:
                emoji = await commands.PartialEmojiConverter().convert(ctx, argument)
            except commands.PartialEmojiConversionFailure:
                raise commands.BadArgument("Could not display info for that emoji...")
        return emoji


class InbetweenNumber(commands.Converter):
    def __init__(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum

    async def convert(self, ctx, argument):
        try:
            val = int(argument)
        except ValueError:
            raise commands.BadArgument('Number needs to be a whole number.')
        if val < self.minimum:
            raise commands.BadArgument(f"You can\'t use a number lower than {self.minimum}")
        elif val > self.maximum:
            raise commands.BadArgument(f"You can\'t use a number higher than {self.maximum}")
        return val


WHITELISTED_HOSTS = ["cdn.discordapp.com", "i.imgur.com", "images.discordapp.net", "media.discordapp.net"]


class Whitelisted_URL:
    def __init__(self, url):
        url_regex = re.compile("https?:\\/\\/(?:www\\.)?.+")
        if not url_regex.match(url):
            raise LightningError("Invalid URL")

        url = yarl.URL(url)

        if url.host not in WHITELISTED_HOSTS:
            raise LightningError(f"`\"{url}\"` is not supported.")

        self.url = url

    @classmethod
    async def convert(cls, ctx, argument):
        return cls(argument)

    def __str__(self):
        return str(self.url)


class Role(commands.RoleConverter):
    """Converts to :class:`discord.Role` but respects hierarchy"""
    async def convert(self, ctx: GuildContext, argument) -> discord.Role:
        role = await super().convert(ctx, argument)

        if role.is_assignable() is False:
            raise HierarchyException("role")

        return role


def convert_to_level_value(argument):
    d = {"user": CommandLevel.User,
         "trusted": CommandLevel.Trusted,
         "mod": CommandLevel.Mod,
         "admin": CommandLevel.Admin}

    if argument.lower() in d:
        return d[argument.lower()]
    else:
        raise InvalidLevelArgument(d.keys(), argument)


def Snowflake(argument) -> int:
    match = re.match(r"[0-9]{15,20}", argument)
    if not match:
        raise commands.BadArgument("That doesn't seem like a snowflake.")

    return int(match.group(0))


def SnowflakeDT(argument) -> datetime:
    return discord.utils.snowflake_time(Snowflake(argument))
