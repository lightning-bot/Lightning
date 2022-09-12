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
import logging
import re
from datetime import datetime

import discord
import yarl
from discord.ext import commands

from lightning.commands import CommandLevel
from lightning.errors import (ChannelPermissionFailure, HierarchyException,
                              InvalidLevelArgument, LightningError)

log = logging.getLogger(__name__)


async def non_guild_user(ctx, user_id: str):
    """
    Used when a Member or User object cannot be resolved.
    """
    try:
        user_id = int(user_id, base=10)
    except ValueError:
        raise commands.BadArgument(f"{user_id} is not a valid member ID.")

    user = ctx.bot.get_user(user_id)
    if not user:
        log.debug(f"User is not cached, switching to API lookup for {user_id}")
        try:
            user = await ctx.bot.fetch_user(user_id)
        except discord.NotFound:
            raise commands.BadArgument(f"\"{user_id}\" could not be found")
        except discord.HTTPException:
            raise commands.BadArgument("An exception occurred while finding this user.")
        else:
            return user
    else:
        return user


class GuildorNonGuildUser(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            target = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            target = await non_guild_user(ctx, argument)
        return target


class TargetMember(commands.Converter):
    def __init__(self, *, fetch_user=True):
        if fetch_user:
            self.user_converter = GuildorNonGuildUser()
        else:
            self.user_converter = commands.MemberConverter()

    async def check_member(self, ctx, member):
        if member.id == ctx.me.id:
            raise commands.BadArgument("Bots can't do actions on themselves.")

        if member.id == ctx.author.id:
            raise commands.BadArgument("You can't do actions on yourself.")

        if isinstance(member, discord.Member):
            if member.id == ctx.guild.owner_id:
                raise commands.BadArgument("You can't do actions on the server owner.")

            if member.top_role >= ctx.author.top_role:
                raise commands.BadArgument("You can't do actions on this member due to hierarchy.")

    async def convert(self, ctx, argument):
        target = await self.user_converter.convert(ctx, argument)
        await self.check_member(ctx, target)
        return target


class ReadableChannel(commands.Converter):
    async def convert(self, ctx, argument):
        channel = await commands.TextChannelConverter().convert(ctx, argument)
        if not channel.permissions_for(ctx.me).read_messages:
            raise ChannelPermissionFailure(f"I don't have permission to view channel {channel.mention}")
        if not ctx.author or not channel.permissions_for(ctx.author).read_messages:
            raise ChannelPermissionFailure(f"You don't have permission to view channel {channel.mention}")
        return channel


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


class LastImage(commands.CustomDefault):
    async def default(self, ctx, param):
        limit = 15
        async for message in ctx.channel.history(limit=limit):
            for embed in message.embeds:
                if embed.thumbnail and embed.thumbnail.url:
                    return embed.thumbnail.url
            for attachment in message.attachments:
                if attachment.url:
                    return attachment.url
        raise commands.BadArgument(f"Couldn't find an image in the last {limit} messages.")


# https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/mod.py#L122
class BannedMember(commands.Converter):
    async def convert(self, ctx, argument):
        if argument.isdigit():
            try:
                return await ctx.guild.fetch_ban(discord.Object(argument))
            except discord.NotFound:
                raise commands.BadArgument("This member has not been banned before.")

        ban_list = await ctx.guild.bans()
        entity = discord.utils.find(lambda u: str(u.user) == argument, ban_list)

        if entity is None:
            raise commands.BadArgument("This member has not been banned before.")
        return entity


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


class Message(commands.Converter):
    async def convert(self, ctx, argument):
        if len(argument) == 2:
            try:
                message = int(argument[0])
            except ValueError:
                raise LightningError("Not a valid message ID.")
            channel = await ReadableChannel().convert(ctx, argument[1])
            return message, channel
        # regex from d.py
        argument = argument[0]
        link_regex = re.compile(
            r'^https?://(?:(ptb|canary)\.)?discord(?:app)?\.com/channels/'
            r'(?:([0-9]{15,21})|(@me))'
            r'/(?P<channel_id>[0-9]{15,21})/(?P<message_id>[0-9]{15,21})/?$'
        )
        match = link_regex.match(argument)
        if not match:
            # Same message from channel...
            try:
                message = int(argument)
            except ValueError:
                raise LightningError("Not a valid message ID.")
            channel = ctx.channel
            return message, channel
        message_id = int(match.group("message_id"))
        channel_id = match.group("channel_id")
        channel = await ReadableChannel().convert(ctx, channel_id)
        return message_id, channel


class GuildID(commands.Converter):
    async def convert(self, ctx, argument):
        if not argument.isdigit():
            raise commands.BadArgument(f"Unable to convert \"{argument}\" to GuildID")
        guild = ctx.bot.get_guild(int(argument))
        if not guild:
            raise commands.BadArgument(f"Unable to convert \"{argument}\" to GuildID")
        return guild


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
    async def convert(self, ctx, argument):
        role = await super().convert(ctx, argument)

        if role.is_assignable() is False:
            raise HierarchyException("role")

        return role


class Prefix(commands.Converter):
    async def convert(self, ctx, argument) -> str:
        user_id = ctx.bot.user.id
        if argument.startswith((f'<@{user_id}>', f'<@!{user_id}>')):
            raise commands.BadArgument('That is a reserved prefix already in use.')
        if len(argument) > 50:
            raise commands.BadArgument('You can\'t have a prefix longer than 50 characters!')
        return argument


def convert_to_level(argument):
    levels = ('trusted', 'mod', 'admin')
    if argument.lower() in levels:
        return argument
    else:
        raise InvalidLevelArgument(levels, argument)


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
