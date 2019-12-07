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

from discord.ext import commands
import discord
from utils.checks import member_at_least_has_staff_role
from utils.errors import BadTarget, ChannelPermissionFailure, LightningError


class WarnNumber(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            val = int(argument)
        except ValueError:
            raise commands.BadArgument('Number needs to be a whole number.')
        if val <= 0:
            raise commands.BadArgument("You can\'t set a warn punishment to zero or less.")
        elif val >= 100:
            raise commands.BadArgument("You can\'t set a warn punishment to 100 or higher!")
        return val


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
        ctx.bot.log.debug("Switching to API Lookup")
        try:
            user = await ctx.bot.fetch_user(user_id)
        except discord.NotFound:
            raise commands.BadArgument(f"\"{user_id}\" could not be found")
        except discord.HTTPException:
            raise commands.BadArgument("An exception occurred while finding this user!")
    return user


class TargetMember(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            target = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            target = await non_guild_user(ctx, argument)
        if target == ctx.bot.user:
            raise BadTarget("You can't do mod actions on me.")
        elif target == ctx.author:
            raise BadTarget("You can't do mod actions on yourself.")
        if isinstance(target, discord.Member):
            if target.guild_permissions.manage_messages or await member_at_least_has_staff_role(ctx, target) \
                or ctx.author.id == ctx.guild.owner.id:
                raise BadTarget("You can't do mod actions on other staff!")
            if ctx.author.top_role < target.top_role:
                raise BadTarget("You can't do mod actions on this user due to role hierarchy.")
        else:
            return target


class ReadableChannel(commands.Converter):
    async def convert(self, ctx, argument):
        channel = await commands.TextChannelConverter().convert(ctx, argument)
        if not channel.guild.me.permissions_in(channel).read_messages:
            raise ChannelPermissionFailure(f"I don't have permission to view channel {channel.mention}")
        if not ctx.author or not channel.permissions_for(ctx.author).read_messages:
            raise ChannelPermissionFailure(f"You don't have permission to view channel {channel.mention}")
        return channel


class SendableChannel(commands.Converter):
    async def convert(self, ctx, argument):
        channel = await commands.TextChannelConverter().convert(ctx, argument)
        if not channel.guild.me.permissions_in(channel).send_messages:
            raise ChannelPermissionFailure("I don't have permission to send "
                                           f"messages in {channel.mention}")
        if not ctx.author or not channel.permissions_for(ctx.author).send_messages:
            raise ChannelPermissionFailure("You don't have permission to "
                                           f"send messages in {channel.mention}")
        return channel


class SafeSend(commands.Converter):
    async def convert(self, ctx, message):
        # Extra Converter to save my life. Fuck @everyone pings
        # I hope this saves my life forever. :blobsweat:
        escape_mentions = str(message).replace("@", "@\u200B")
        content = await commands.clean_content().convert(ctx, str(escape_mentions))
        return content


class LastImage(commands.Converter):
    """Converter to handle images"""
    async def default(self, ctx, param):
        async for message in ctx.channel.history(limit=15):
            # Capping it off at 15 for safety measures
            for embed in message.embeds:
                if embed.thumbnail and embed.thumbnail.proxy_url:
                    return embed.thumbnail.proxy_url
            for attachment in message.attachments:
                if attachment.proxy_url:
                    return attachment.proxy_url
        raise discord.ext.errors.MissingRequiredArgument("Couldn't "
                                                         "find an image in the last "
                                                         "15 messages")


# https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/mod.py#L122
class BannedMember(commands.Converter):
    async def convert(self, ctx, argument):
        ban_list = await ctx.guild.bans()
        try:
            member_id = int(argument, base=10)
            entity = discord.utils.find(lambda u: u.user.id == member_id, ban_list)
        except ValueError:
            entity = discord.utils.find(lambda u: str(u.user) == argument, ban_list)

        if entity is None:
            raise commands.BadArgument("Not a valid previously-banned member.")
        return entity


class ValidCommandName(commands.Converter):
    async def convert(self, ctx, argument):
        lowered = argument.lower()

        valid_commands = {
            c.qualified_name
            for c in ctx.bot.walk_commands()
            if c.cog_name not in ('Configuration', 'Owner', 'TasksManagement',
                                  'Jishaku', 'Bolt', 'Git')
        }

        if lowered not in valid_commands:
            raise LightningError(f'Command {lowered!r} is not valid.')

        return lowered
