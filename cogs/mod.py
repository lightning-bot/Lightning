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

import asyncio
import io
import json
import time
from datetime import datetime, timedelta

import asyncpg
import discord
from async_lru import alru_cache
from bolt.paginator import Pages
from bolt.time import get_utc_timestamp
from discord.ext import commands

from utils import converters, modlog_formatter
from utils.checks import is_staff_or_has_perms
from utils.database import GuildModConfig
from utils.errors import MuteRoleError, NoWarns, TimersUnavailable
from utils.time import FutureTime, natural_timedelta
from utils.user_log import (get_userlog, set_userlog, userlog,
                            userlog_event_types)


class WarnPages(Pages):
    """Similar to FieldPages except entries should be a list of
    tuples having (key, value) to show as embed fields instead.
    """
    def __init__(self, set_author, ctx, entries, *, per_page=4):
        super().__init__(ctx, entries=entries, per_page=per_page)
        self.set_author = set_author

    def prepare_embed(self, entries, page, *, first=False):
        self.embed.clear_fields()
        self.embed.description = discord.Embed.Empty
        self.embed.set_author(name=self.set_author)

        for key, value in entries:
            self.embed.add_field(name=key, value=value, inline=False)

        if self.maximum_pages > 1:
            if self.show_entry_count:
                text = f'Page {page}/{self.maximum_pages} ({len(self.entries)} entries)'
            else:
                text = f'Page {page}/{self.maximum_pages}'

            self.embed.set_footer(text=text)


class Mod(commands.Cog):
    """
    Moderation and server management commands.
    """
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    def cog_unload(self):
        # Close our cache
        self.get_mod_config.close()

    def mod_reason(self, ctx, reason: str):
        if reason:
            to_return = f"{ctx.author} (ID: {ctx.author.id}): {reason}"
        else:
            to_return = f"Action done by {ctx.author} (ID: {ctx.author.id})"
        if len(to_return) > 512:
            raise commands.BadArgument('Reason is too long!')
        return to_return

    @alru_cache(maxsize=32)
    async def get_mod_config(self, guild_id):
        """
        Returns: :class: `GuildModConfig` if guild_id is in the database,
        else returns None
        """
        query = """SELECT * FROM guild_mod_config WHERE guild_id=$1"""
        ret = await self.bot.db.fetchrow(query, guild_id)
        if not ret:
            return None
        return GuildModConfig(ret)

    async def channelid_send(self, guild_id: int, channel_id: int, item, message, **kwargs):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            return await self.forbidden_removal(item, guild_id)
        try:
            msg = await channel.send(message, **kwargs)
            return msg
        except discord.Forbidden:
            await self.forbidden_removal(item, guild_id)

    async def forbidden_removal(self, item, guild_id):
        query = """UPDATE guild_mod_config
                   SET log_channels = log_channels - $1
                   WHERE guild_id=$2;"""
        await self.bot.db.execute(query, item, guild_id)
        self.get_mod_config.invalidate(self, guild_id)

    async def set_user_restrictions(self, guild_id: int, user_id: int, role_id: int):
        query = """INSERT INTO user_restrictions (guild_id, user_id, role_id)
                   VALUES ($1, $2, $3)
                """
        return await self.bot.db.execute(query)

    async def remove_user_restriction(self, guild_id: int,
                                      user_id: int, role_id: int):
        query = """DELETE FROM user_restrictions
                   WHERE guild_id=$1
                   AND user_id=$2
                   AND role_id=$3;
                """
        con = await self.bot.db.acquire()
        try:
            await con.execute(query, guild_id, user_id, role_id)
        finally:
            await self.bot.db.release(con)

    # async def insert_into_muted(self, guild_id):
    #    query = """INSERT INTO guild_mod_config (guild_id, muted)
    #               VALUES $1, $2::int[]  ON CONFLICT (guild_id)
    #               DO UPDATE SET
    #                    muted = EXCLUDED.muted;"""

    async def purged_txt(self, ctx, limit):

        """Makes a file containing the limit of messages purged."""
        log_t = f"Archive of {ctx.channel} (ID: {ctx.channel.id}) "\
                f"made on {datetime.utcnow()}\n\n\n"
        async for log in ctx.channel.history(limit=limit):
            # .strftime('%X/%H:%M:%S') but no for now
            log_t += f"[{log.created_at}]: {log.author} - {log.clean_content}"
            if log.attachments:
                for attach in log.attachments:
                    log_t += f"{attach.url}\n"
            else:
                log_t += "\n"

        aiostring = io.StringIO()
        aiostring.write(log_t)
        aiostring.seek(0)
        aiofile = discord.File(aiostring, filename=f"{ctx.channel}_purge.txt")
        # try:
        #    guild = self.bot.get_guild(527887739178188830)
        #    ch = guild.get_channel(639130406582747147)
        #    ret = await ch.send(file=aiofile)
        return aiofile

    @commands.guild_only()  # This isn't needed but w/e :shrugkitty:
    @commands.bot_has_permissions(kick_members=True)
    @is_staff_or_has_perms("Moderator", kick_members=True)
    @commands.command()
    async def kick(self, ctx, target: converters.TargetMember, *, reason: str = ""):
        """Kicks a user.

        In order to use this command, you must either have
        Kick Members permission or a role that
        is assigned as a Moderator or above in the bot."""

        dm_message = f"You were kicked from {ctx.guild.name}."
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
        dm_message += "\n\nYou are able to rejoin the server," \
                      " but please be sure to behave when participating again."

        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents kick issues in cases where user blocked bot
            # or has DMs disabled
            pass
        await ctx.guild.kick(target, reason=f"{self.mod_reason(ctx, reason)}")
        await ctx.send(f"{target} has been kicked. 👌 ")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="kick", target=target,
                                                         moderator=ctx.author, reason=reason)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("kick", target, ctx.author,
                                                            reason=reason, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()  # This isn't needed but w/e :shrugkitty:
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    @commands.command()
    async def ban(self, ctx, target: converters.TargetNonGuildMember, *, reason: str = ""):
        """Bans a user.

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""
        dm_message = f"You were banned from {ctx.guild.name}."
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
        dm_message += "\n\nThis ban does not expire."
        dm_message += "\n\nIf you believe this to be in error, please message the staff."

        if isinstance(target, discord.Member):
            try:
                await target.send(dm_message)
            except discord.errors.Forbidden:
                # Prevents ban issues in cases where user blocked bot
                # or has DMs disabled
                pass

        await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, reason)}",
                            delete_message_days=0)
        await ctx.safe_send(f"{target} is now b&. 👍")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="ban", target=target,
                                                         moderator=ctx.author, reason=reason)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("ban", target, ctx.author,
                                                            reason=reason, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    async def warn_count_check(self, ctx, target, reason: str = ""):
        msg = f"You were warned in {ctx.guild.name}."
        if reason:
            msg += " The given reason is: " + reason
        warn_count = await userlog(self.bot, ctx.guild, target.id,
                                   ctx.author, reason,
                                   "warns", target.name)
        msg += f"\n\nThis is warn #{warn_count}."
        punishable_warn = await self.get_mod_config(ctx.guild.id)
        if not punishable_warn:
            if isinstance(target, discord.Member):
                try:
                    await target.send(msg)
                    return warn_count
                except discord.Forbidden:
                    return warn_count
            else:
                return warn_count
        if punishable_warn.warn_kick:
            if warn_count == punishable_warn.warn_kick - 1:
                msg += " __The next warn will automatically kick.__"
            if warn_count == punishable_warn.warn_kick:
                msg += "\n\nYou were kicked because of this warning. " \
                       "You can join again right away. "
        if punishable_warn.warn_ban:
            if warn_count == punishable_warn.warn_ban - 1:
                msg += "This is your final warning. " \
                       "Do note that " \
                       "**one more warn will result in a ban**."
            if warn_count >= punishable_warn.warn_ban:
                msg += f"\n\nYou were automatically banned due to reaching "\
                       f"the guild's warn ban limit of "\
                       f"{punishable_warn.warn_ban} warnings."
                msg += "\nIf you believe this to be in error, please message the staff."
        if isinstance(target, (discord.Member, discord.User)):
            try:
                await target.send(msg)
            except discord.errors.Forbidden:
                # Prevents issues in cases where user blocked bot
                # or has DMs disabled
                pass
            if punishable_warn.warn_kick:
                if warn_count == punishable_warn.warn_kick:
                    opt_reason = f"[WarnKick] Reached {warn_count} warns. "
                    if reason:
                        opt_reason += f"{reason}"
                    await ctx.guild.kick(target, reason=f"{self.mod_reason(ctx, opt_reason)}")
        if punishable_warn.warn_ban:
            if warn_count >= punishable_warn.warn_ban:  # just in case
                opt_reason = f"[WarnBan] Exceeded WarnBan Limit ({warn_count}). "
                if reason:
                    opt_reason += f"{reason}"
                await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, opt_reason)}",
                                    delete_message_days=0)
        return warn_count

    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True, ban_members=True)
    @is_staff_or_has_perms("Helper", manage_messages=True)
    @commands.group(invoke_without_command=True)
    async def warn(self, ctx, target: converters.TargetMember, *, reason: str = ""):
        """Warns a user.

        In order to use this command, you must either have
        Manage Messages permission or a role
        that is assigned as a Helper or above in the bot."""
        warn_count = await self.warn_count_check(ctx, target, reason)

        await ctx.safe_send(f"{target} warned. "
                            f"User has {warn_count} warning(s).")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="warn", target=target,
                                                         moderator=ctx.author, reason=reason,
                                                         warn_count=warn_count)
                await self.channelid_send(ctx.guild.id, int(logch), "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("warn", target, ctx.author,
                                                            reason=reason, time=ctx.message.created_at,
                                                            warn_count=warn_count)
                await self.channelid_send(ctx.guild.id, int(logch), "modlog_chan", message)

    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True, ban_members=True)
    @is_staff_or_has_perms("Admin", manage_guild=True)
    @warn.group(name="punishments", aliases=['punishment'], invoke_without_command=True)
    async def warn_punish(self, ctx):
        """Configures warn punishments for the server.

        In order to use this command, you must either have
        Manage Guild permission or a role that
        is assigned as a Admin or above in the bot."""
        ret = await self.get_mod_config(ctx.guild.id)
        if not ret:
            return await ctx.send("Warn punishments have not been setup.")
        if ret.warn_kick is None and ret.warn_ban is None:
            return await ctx.send("Warn punishments have not been setup.")
        msg = ""
        if ret.warn_kick:
            msg += f"Kick: at {ret.warn_kick} warns\n"
        if ret.warn_ban:
            msg += f"Ban: at {ret.warn_ban}+ warns\n"
        await ctx.send(msg)

    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True, ban_members=True)
    @is_staff_or_has_perms("Admin", manage_guild=True)
    @warn_punish.command(name="kick")
    async def warn_kick(self, ctx, number: converters.WarnNumber):
        """Configures the warn kick punishment.

        This kicks the member after acquiring a certain amount of warns.

        In order to use this command, you must either have
        Manage Guild permission or a role that
        is assigned as a Admin or above in the bot."""
        query = """SELECT warn_ban
                   FROM guild_mod_config
                   WHERE guild_id=$1;"""
        ban_count = await self.bot.db.fetchval(query, ctx.guild.id)
        if ban_count:
            if number >= ban_count:
                return await ctx.send("You cannot set the same or a higher value "
                                      "for warn kick punishment "
                                      "as the warn ban punishment.")
        query = """INSERT INTO guild_mod_config (guild_id, warn_kick)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET warn_kick = EXCLUDED.warn_kick;
                """
        await self.bot.db.execute(query, ctx.guild.id, number)
        self.get_mod_config.invalidate(self, ctx.guild.id)
        await ctx.send(f"Users will now get kicked if they reach "
                       f"{number} warns.")

    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True, ban_members=True)
    @is_staff_or_has_perms("Admin", manage_guild=True)
    @warn_punish.command(name="ban")
    async def warn_ban(self, ctx, number: converters.WarnNumber):
        """Configures the warn ban punishment.

        This bans the member after acquiring a certain
        amount of warns or higher.

        In order to use this command, you must either have
        Manage Guild permission or a role that
        is assigned as a Admin or above in the bot."""
        query = """SELECT warn_kick
                   FROM guild_mod_config
                   WHERE guild_id=$1;"""
        kick_count = await self.bot.db.fetchval(query, ctx.guild.id)
        if kick_count:
            if number <= kick_count:
                return await ctx.send("You cannot set the same or a lesser value "
                                      "for warn ban punishment "
                                      "as the warn kick punishment.")
        query = """INSERT INTO guild_mod_config (guild_id, warn_ban)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET warn_ban = EXCLUDED.warn_ban;
                """
        await self.bot.db.execute(query, ctx.guild.id, number)
        self.get_mod_config.invalidate(self, ctx.guild.id)
        await ctx.send(f"Users will now get banned if they reach "
                       f"{number} or a higher amount of warns.")

    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True, ban_members=True)
    @is_staff_or_has_perms("Admin", manage_guild=True)
    @warn_punish.command(name="clear")
    async def warn_remove(self, ctx):
        """Removes all warn punishment configuration.

        In order to use this command, you must either have
        Manage Guild permission or a role that
        is assigned as a Admin or above in the bot."""
        query = """UPDATE guild_mod_config
                   SET warn_ban=NULL,
                   warn_kick=NULL
                   WHERE guild_id=$1;
                """
        ret = await self.bot.db.execute(query, ctx.guild.id)
        self.get_mod_config.invalidate(self, ctx.guild.id)
        if ret == "DELETE 0":
            return await ctx.send("Warn punishments were never configured!")
        await ctx.send("Removed warn punishment configuration!")

    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True)
    @is_staff_or_has_perms("Moderator", manage_messages=True)
    @commands.command()
    async def purge(self, ctx, message_count: int, *, reason: str = ""):
        """Purges a channel's last x messages.

        In order to use this command, You must either have
        Manage Messages permission or a role that
        is assigned as a Moderator or above in the bot."""
        if message_count > 100:
            return await ctx.send("You cannot purge more than 100 messages at a time!")
        fi = await self.purged_txt(ctx, message_count)
        try:
            pmsg = await ctx.channel.purge(limit=message_count)
        except Exception as e:
            self.bot.log.error(e)
            return await ctx.send('❌ Cannot purge messages!')
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="purge", target=ctx.channel,
                                                         moderator=ctx.author, reason=reason,
                                                         messages=len(pmsg))
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message, file=fi)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("purge", ctx.channel, ctx.author,
                                                            reason=reason, time=ctx.message.created_at,
                                                            messages=len(pmsg))
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message, file=fi)

    @commands.guild_only()
    @commands.command(aliases=["nick"])
    @is_staff_or_has_perms("Helper", manage_nicknames=True)
    async def nickname(self, ctx, target: discord.Member, *, nickname: str = ''):
        """Sets a user's nickname.

        In order to use this command, you must either have
        Manage Nicknames permission or a role that
        is assigned as a Helper or above in the bot."""
        try:
            await target.edit(nick=nickname, reason=f"{self.mod_reason(ctx, reason='')}")
        except discord.errors.Forbidden:
            await ctx.send("I can't change their nickname!")
            return

        await ctx.safe_send(f"Successfully changed {target.name}'s nickname.")

    async def get_mute_role(self, ctx):
        """Gets the guild's mute role if it exists"""
        config = await self.get_mod_config(ctx.guild.id)
        if config and config.mute_role_id:
            if config.mute_role(ctx):
                return config.mute_role(ctx)
            else:
                raise MuteRoleError("You do not have a mute role setup!")
        else:
            raise MuteRoleError("You do not have a mute role setup!")

    @commands.guild_only()
    @commands.command(aliases=['muteuser'])
    @commands.bot_has_permissions(manage_roles=True)
    @is_staff_or_has_perms("Moderator", manage_roles=True)
    async def mute(self, ctx, target: converters.TargetMember, *, reason: str = ""):
        """Mutes a user.

        In order to use this command, you must either have
        Manage Roles permission or a role that
        is assigned as a Moderator or above in the bot."""
        role = await self.get_mute_role(ctx)

        dm_message = f"You were muted on {ctx.guild.name}!"
        opt_reason = "[Mute] "
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
            opt_reason += f"{reason}"
        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents issues in cases where user blocked bot
            # or has DMs disabled
            pass

        await target.add_roles(role, reason=f"{self.mod_reason(ctx, opt_reason)}")
        await self.set_user_restrictions(ctx.guild.id, target.id, role.id)
        await ctx.safe_send(f"{target} can no longer speak.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="mute", target=target,
                                                         moderator=ctx.author, reason=reason)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("mute", target, ctx.author,
                                                            reason=reason, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    async def mute_role_check(self, guild_id, target_id, role_id):
        query = """SELECT * FROM user_restrictions
                WHERE guild_id=$1 AND user_id=$2 AND role_id=$3"""
        return await self.bot.db.fetchval(query, guild_id, target_id, role_id)

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(manage_roles=True)
    @is_staff_or_has_perms("Moderator", manage_roles=True)
    async def unmute(self, ctx, target: discord.Member, *,
                     reason: commands.clean_content = ""):
        """Unmutes a user.

        In order to use this command, you must either have
        Manage Roles permission or a role that
        is assigned as a Moderator or above in the bot."""
        role = await self.get_mute_role(ctx)
        role_check_2 = await self.mute_role_check(ctx.guild.id, target.id, role.id)
        if role not in target.roles or role_check_2 is None:
            return await ctx.send('This user is not muted!')
        await target.remove_roles(role, reason=f"{self.mod_reason(ctx, '[Unmute]')}")
        await self.remove_user_restriction(ctx.guild.id, target.id, role.id)
        await ctx.safe_send(f"{target} can now speak again.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="unmute", target=target,
                                                         moderator=ctx.author, reason=reason)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if ch['log_format'] == "lightning":
                message = modlog_formatter.lightning_format("unmute", target, ctx.author,
                                                            reason=reason, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    async def unban(self, ctx, target: converters.BannedMember, *, reason: str = ""):
        """Unbans a user.

        You can pass either the ID of the banned member or the Name#Discrim
        combination of the member. The target's ID is easier to use.

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""

        await ctx.guild.unban(target.user, reason=f"{self.mod_reason(ctx, reason)}")
        await ctx.safe_send(f"{target.user} is now unbanned.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="unban", target=target.user,
                                                         moderator=ctx.author, reason=reason)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if ch['log_format'] == "lightning":
                message = modlog_formatter.lightning_format("unban", target.user, ctx.author,
                                                            reason=reason, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    @commands.command(aliases=['tempban'])
    async def timeban(self, ctx, target: converters.TargetNonGuildMember,
                      duration: FutureTime, *, reason: str = ""):
        """Bans a user for a specified amount of time.

        The duration can be a short time format such as "30d",
        a more human duration format such as "until Monday at 7PM",
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC.

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""
        duration_text = get_utc_timestamp(duration.dt)
        timed_txt = natural_timedelta(duration.dt, source=ctx.message.created_at)
        duration_text = f"{timed_txt} ({duration_text})"
        timer = self.bot.get_cog('TasksManagement')
        if not timer:
            raise TimersUnavailable
        ext = {"guild_id": ctx.guild.id, "user_id": target.id,
               "mod_id": ctx.author.id}
        await timer.add_job("timeban", ctx.message.created_at,
                            duration.dt, ext)
        if isinstance(target, (discord.Member, discord.User)):
            dm_message = f"You were banned from {ctx.guild.name}."
            if reason:
                dm_message += f" The given reason is: \"{reason}\"."
            dm_message += f"\n\nThis ban will expire in {duration_text}."
            try:
                await target.send(dm_message)
            except discord.errors.Forbidden:
                pass
        if reason:
            opt_reason = f"{reason} (Timeban expires in {duration_text})"
        else:
            opt_reason = f" (Timeban expires in {duration_text})"
        await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, opt_reason)}",
                            delete_message_days=0)
        await ctx.safe_send(f"{str(target)} is now b&. 👍 "
                            f"It will expire in {duration_text}.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="timeban", target=target,
                                                         moderator=ctx.author, reason=reason,
                                                         expiry=duration_text)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("timeban", target, ctx.author,
                                                            reason=reason, time=ctx.message.created_at,
                                                            expiry=duration_text)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.command(aliases=['tempmute'])
    @commands.bot_has_permissions(manage_roles=True)
    @is_staff_or_has_perms("Moderator", manage_roles=True)
    async def timemute(self, ctx, target: converters.TargetMember,
                       duration: FutureTime, *, reason: str = ""):
        """Mutes a user for a specified amount of time.

        The duration can be a short time format such as "30d",
        a more human duration format such as "until Monday at 7PM",
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC.

        In order to use this command, you must either have
        Manage Roles permission or a role that
        is assigned as a Moderator or above in the bot."""
        role = await self.get_mute_role(ctx)
        duration_text = get_utc_timestamp(duration.dt)
        timed_txt = natural_timedelta(duration.dt, source=ctx.message.created_at)
        duration_text = f"{timed_txt} ({duration_text})"
        timer = self.bot.get_cog('TasksManagement')
        if not timer:
            raise TimersUnavailable
        ext = {"guild_id": ctx.guild.id, "user_id": target.id,
               "role_id": role.id, "mod_id": ctx.author.id}
        await timer.add_job("timed_restriction", ctx.message.created_at,
                            duration.dt, ext)
        dm_message = f"You were muted on {ctx.guild.name}!"
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
        dm_message += f"\n\nThis mute will expire in {duration_text}."

        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents mute issues in cases where user blocked bot
            # or has DMs disabled
            pass
        if reason:
            opt_reason = f"{reason} (Timemute expires in {duration_text})"
        else:
            opt_reason = f" (Timemute expires in {duration_text})"
        if isinstance(target, discord.Member):
            await target.add_roles(role, reason=f"{self.mod_reason(ctx, opt_reason)}")
        try:
            await self.set_user_restrictions(ctx.guild.id, target.id, role.id)
        except asyncpg.UniqueViolationError:
            pass
        await ctx.safe_send(f"{str(target)} can no longer speak. "
                            f"It will expire in {duration_text}.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="timemute", target=target,
                                                         moderator=ctx.author, reason=reason,
                                                         expiry=duration_text)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("timemute", target, ctx.author,
                                                            reason=reason, time=ctx.message.created_at,
                                                            expiry=duration_text)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.command(aliases=['temprole'])
    @commands.bot_has_permissions(manage_roles=True)
    @is_staff_or_has_perms("Moderator", manage_roles=True)
    async def temprolerestrict(self, ctx, target: converters.TargetMember,
                               role: discord.Role, duration: FutureTime,
                               *, reason: str = ""):
        """Temporarily restricts a role to a user for a specified amount of time.

        The duration can be a short time format such as "30d",
        a more human duration format such as "until Monday at 7PM",
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC.

        In order to use this command, you must either have
        Manage Roles permission or a role that
        is assigned as a Moderator or above in the bot."""
        dtxt = get_utc_timestamp(duration.dt)
        timed_txt = natural_timedelta(duration.dt, source=ctx.message.created_at)
        duration_text = f"{timed_txt} ({dtxt})"
        timer = self.bot.get_cog('TasksManagement')
        if not timer:
            raise TimersUnavailable
        ext = {"guild_id": ctx.guild.id, "user_id": target.id,
               "role_id": role.id, "mod_id": ctx.author.id}
        await timer.add_job("timed_restriction", ctx.message.created_at,
                            duration.dt, ext)
        # Role restricts don't have a DM reason
        if reason:
            opt_reason = f"{reason} (Role restriction expires in {duration_text})"
        else:
            opt_reason = f" (Role restriction expires in {duration_text})"
        if isinstance(target, discord.Member):
            await target.add_roles(role, reason=f"{self.mod_reason(ctx, opt_reason)}")
        await self.set_user_restrictions(ctx.guild.id, target.id, role.id)
        await ctx.safe_send(f"Restricted role: {role.name} to {target}. "
                            f"It will expire in {duration_text}.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_temprole(target=target,
                                                           mod=ctx.author, reason=reason,
                                                           expiry=duration_text, role=role)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("temprole", target, ctx.author,
                                                            reason=reason, time=ctx.message.created_at,
                                                            expiry=duration_text)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @is_staff_or_has_perms("Moderator", manage_channels=True)
    @commands.command(aliases=['lockdown'])
    async def lock(self, ctx, channel: discord.TextChannel = None):
        """Locks down the channel mentioned.

        Sets the channel permissions as @everyone can't send messages.

        If no channel was mentioned, it locks the channel the command was used in.

        In order to use this command, You must either have
        Manage Channels permission or a role that
        is assigned as a Moderator or above in the bot."""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).send_messages is False:
            await ctx.send(f"🔒 {channel.mention} is already locked down. "
                           f"Use `{ctx.prefix}unlock` to unlock.")
            return

        await channel.set_permissions(ctx.guild.default_role, send_messages=False, add_reactions=False)
        await ctx.send(f"🔒 {channel.mention} is now locked.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="lockdown", target=None,
                                                         moderator=ctx.author, reason=None,
                                                         lockdown_channel=channel)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("lockdown", channel, ctx.author,
                                                            reason=None, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @is_staff_or_has_perms("Admin", manage_channels=True)
    @commands.command(aliases=['hard-lock'])
    async def hlock(self, ctx, channel: discord.TextChannel = None):
        """Hard locks a channel.

        Sets the channel permissions as @everyone can't
        send messages or read messages in the channel.

        If no channel was mentioned, it hard locks the channel the command was used in.

        In order to use this command, you must either have
        Manage Channels permission or a role that
        is assigned as an Admin or above in the bot."""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).read_messages is False:
            await ctx.send(f"🔒 {channel.mention} is already hard locked. "
                           f"Use `{ctx.prefix}hard-unlock` to unlock the channel.")
            return

        await channel.set_permissions(ctx.guild.default_role, read_messages=False)
        await ctx.send(f"🔒 {channel.mention} is now hard locked.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="hard-lockdown", target=None,
                                                         moderator=ctx.author, reason=None,
                                                         lockdown_channel=channel)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("hard-lockdown", channel, ctx.author,
                                                            reason=None, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @is_staff_or_has_perms("Moderator", manage_channels=True)
    @commands.command()
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        """Unlocks the channel mentioned.

        If no channel was mentioned, it unlocks the channel the command was used in.

        In order to use this command, You must either have
        Manage Channels permission or a role that
        is assigned as a Moderator or above in the bot."""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).send_messages is None:
            await ctx.send(f"🔓 {channel.mention} is already unlocked.")
            return

        await channel.set_permissions(ctx.guild.default_role, send_messages=None, add_reactions=None)
        await ctx.send(f"🔓 {channel.mention} is now unlocked.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="unlock", target=None,
                                                         moderator=ctx.author, reason=None,
                                                         lockdown_channel=channel)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("unlock", channel, ctx.author,
                                                            reason=None, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @is_staff_or_has_perms("Admin", manage_channels=True)
    @commands.command(aliases=['hard-unlock'])
    async def hunlock(self, ctx, channel: discord.TextChannel = None):
        """Hard unlocks the channel mentioned.

        If no channel was mentioned, it unlocks the channel the command was used in.

        In order to use this command, You must either have
        Manage Channels permission or a role that
        is assigned as an Admin or above in the bot."""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).read_messages is None:
            await ctx.send(f"🔓 {channel.mention} is already unlocked.")
            return

        await channel.set_permissions(ctx.guild.default_role, read_messages=None)
        await ctx.send(f"🔓 {channel.mention} is now unlocked.")
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="unlock", target=None,
                                                         moderator=ctx.author, reason=None,
                                                         lockdown_channel=channel)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("unlock", channel, ctx.author,
                                                            reason=None, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True)
    @is_staff_or_has_perms("Moderator", manage_messages=True)
    @commands.command()
    async def pin(self, ctx, message_id: int, channel: discord.TextChannel = None):
        """Pins a message by ID."""
        if not channel:
            channel = ctx.channel
        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send("Message ID not found.")
        try:
            await msg.pin()
        except discord.HTTPException as e:
            return await self.bot.create_error_ticket(ctx, "Error", e)
        await ctx.send("\N{OK HAND SIGN}")

    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True)
    @is_staff_or_has_perms("Moderator", manage_messages=True)
    @commands.command()
    async def unpin(self, ctx, message_id: int, channel: discord.TextChannel = None):
        """Unpins a message by ID."""
        if not channel:
            channel = ctx.channel
        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send("Message ID not found.")
        try:
            await msg.unpin()
        except discord.HTTPException as e:
            return await self.bot.create_error_ticket(ctx, "Error", e)
        await ctx.send("\N{OK HAND SIGN}")

    @commands.guild_only()
    @is_staff_or_has_perms("Moderator", manage_messages=True)
    @commands.command()
    async def clean(self, ctx, search: int = 100,
                    channel: discord.TextChannel = None):
        """Cleans the bot's messages from the channel specified.

        If no channel is specified, the bot deletes its
        messages from the channel the command was run in.

        If a search number is specified, it will search
        that many messages from the bot in the specified channel
        and clean them.

        In order to use this command, you must either have
        Manage Messages permission or a role that
        is assigned as a Moderator or above in the bot.
        """
        if channel is None:
            channel = ctx.channel
        if (search > 100):
            raise commands.BadArgument("Cannot purge more than 100 messages.")
        has_perms = ctx.channel.permissions_for(ctx.guild.me).manage_messages
        await channel.purge(limit=search, check=lambda b: b.author == ctx.bot.user,
                            before=ctx.message.created_at,
                            after=datetime.utcnow() - timedelta(days=14),
                            bulk=has_perms)
        await ctx.send("\N{OK HAND SIGN}", delete_after=15)

    @commands.Cog.listener()
    async def on_timeban_job_complete(self, jobinfo):
        ext = json.loads(jobinfo['extra'])
        guild = self.bot.get_guild(ext['guild_id'])
        if guild is None:
            # Bot was kicked.
            return
        try:
            uid = await self.bot.fetch_user(ext['user_id'])
        except Exception:
            uid = discord.Object(id=ext['user_id'])
        moderator = guild.get_member(ext['mod_id'])
        if moderator is None:
            try:
                moderator = await self.bot.fetch_user(ext['mod_id'])
            except Exception:
                # Discord Broke/Failed/etc.
                mod = f"Moderator ID {ext['mod_id']}"
            else:
                mod = f'{moderator} (ID: {moderator.id})'
        else:
            mod = f'{moderator} (ID: {moderator.id})'
        reason = f"Timed ban made by {mod} at {jobinfo['created']} expired"
        await guild.unban(uid, reason=reason)
        ch = await self.get_mod_config(guild_id=guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_time_ban_expired(uid, moderator, jobinfo['created'])
                await self.channelid_send(ext['guild_id'], logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_time_ban_expired(uid, moderator, jobinfo['created'],
                                                                      jobinfo['expiry'])
                await self.channelid_send(ext['guild_id'], logch, "modlog_chan", message)

    @commands.Cog.listener()
    async def on_timed_restriction_job_complete(self, jobinfo):
        ext = json.loads(jobinfo['extra'])
        guild = self.bot.get_guild(ext['guild_id'])
        if await self.mute_role_check(ext['guild_id'],
                                      ext['user_id'],
                                      ext['role_id']) is None:
            return
        if guild is None:
            # Bot was kicked.
            return
        moderator = guild.get_member(ext['mod_id'])
        if moderator is None:
            try:
                mod = await self.bot.fetch_user(ext['mod_id'])
            except Exception:
                # Discord Broke/Failed/etc.
                mod = f"Moderator ID {ext['mod_id']}"
            else:
                mod = f'{moderator} (ID: {moderator.id})'
        else:
            mod = f'{moderator} (ID: {moderator.id})'
        role = guild.get_role(ext['role_id'])
        if role is None:
            # Role was deleted or something.
            await self.remove_user_restriction(guild.id,
                                               ext['user_id'],
                                               ext['role_id'])
            return
        user = guild.get_member(ext['user_id'])
        if user is None:
            # User left so we remove the restriction and return.
            await self.remove_user_restriction(guild.id,
                                               ext['user_id'],
                                               ext['role_id'])
            ch = await self.get_mod_config(guild_id=guild.id)
            if not ch:
                return
            logch = ch.has_log_channel("modlog_chan")
            if logch is not None:
                logch, logstyle = logch
                if logstyle == "kurisu":
                    message = modlog_formatter.kurisu_format('timed_restriction_removed',
                                                             ext['user_id'],
                                                             mod, role=role,
                                                             job_creation=jobinfo['created'])
                    await self.channelid_send(ext['guild_id'], logch, "modlog_chan", message)
                if logstyle == "lightning":
                    message = modlog_formatter.lightning_format('timed_restriction_removed',
                                                                ext['user_id'],
                                                                mod, reason=None,
                                                                time=jobinfo['expiry'], role=role)
                    await self.channelid_send(ext['guild_id'], logch, "modlog_chan", message)
            return
        reason = f"Timed restriction made by {mod} at "\
                 f"{get_utc_timestamp(jobinfo['created'])} expired"
        await self.remove_user_restriction(guild.id,
                                           user.id,
                                           role.id)
        await user.remove_roles(role, reason=reason)
        ch = await self.get_mod_config(guild_id=guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format('timed_restriction_removed',
                                                         user,
                                                         mod, role=role,
                                                         job_creation=jobinfo['created'])
                await self.channelid_send(ext['guild_id'], logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format('timed_restriction_removed',
                                                            user,
                                                            mod, reason=None,
                                                            time=jobinfo['expiry'], role=role)
                await self.channelid_send(ext['guild_id'], logch, "modlog_chan", message)

# Most commands here taken from robocop-ngs mod.py
# https://github.com/aveao/robocop-ng/blob/master/cogs/mod_user.py
# robocop-ng is MIT licensed

    async def get_userlog_embed_for_id(self, ctx, uid: str, name: str, guild,
                                       own: bool = False, event=""):
        own_note = " Good for you!" if own else ""
        wanted_events = ["warns", "bans", "kicks", "mutes"]
        if event:
            wanted_events = [event]
        userlog = await get_userlog(self.bot, guild)

        if uid not in userlog:
            embed = discord.Embed(title=f"Warns for {name}")
            embed.description = f"There are none!{own_note} (no entry)"
            embed.color = discord.Color.green()
            return await ctx.send(embed=embed)
        entries = []
        for event_type in wanted_events:
            if event_type in userlog[uid] and userlog[uid][event_type]:
                event_name = userlog_event_types[event_type]
                for idx, event in enumerate(userlog[uid][event_type]):
                    issuer = "" if own else f"Issuer: {event['issuer_name']} " \
                                            f"({event['issuer_id']})\n"
                    entries.append((f"{event_name} {idx + 1}: "
                                    f"{event['timestamp']}",
                                    issuer + f"Reason: {event['reason']}"))
        if len(entries) == 0:
            embed = discord.Embed(title=f"Warns for {name}")
            embed.description = f"There are none!{own_note}"
            embed.color = 0x2ecc71
            return await ctx.send(embed=embed)
        embed = WarnPages(f"Warns for {name}", ctx, entries=entries, per_page=5)
        embed.embed.color = 0xf51515
        return await embed.paginate()

    async def clear_event_from_id(self, uid: str, event_type, guild):
        userlog = await get_userlog(self.bot, guild)
        if uid not in userlog:
            raise NoWarns(uid)
        event_count = len(userlog[uid][event_type])
        if not event_count:
            raise NoWarns(uid)
        userlog[uid][event_type] = []
        await set_userlog(self.bot, guild, userlog)
        return f"<@{uid}> no longer has any {event_type}!"

    async def delete_event_from_id(self, uid: str, idx: int, event_type, guild):
        userlog = await get_userlog(self.bot, guild)
        if uid not in userlog:
            raise NoWarns(uid)
        event_count = len(userlog[uid][event_type])
        if not event_count:
            raise NoWarns(uid)
        if idx > event_count:
            return "Index is higher than " \
                   f"count ({event_count})!"
        if idx < 1:
            return "Index is below 1!"
        event = userlog[uid][event_type][idx - 1]
        event_name = userlog_event_types[event_type]
        embed = discord.Embed(color=0xf51515,
                              title=f"{event_name} {idx} on "
                                    f"{event['timestamp']}",
                              description=f"Issuer: {event['issuer_name']}\n"
                                          f"Reason: {event['reason']}")
        del userlog[uid][event_type][idx - 1]
        await set_userlog(self.bot, guild, userlog)
        return embed

    @commands.guild_only()
    @is_staff_or_has_perms("Helper", manage_messages=True)
    @commands.command(name="listwarns")
    async def userlog_cmd(self, ctx, *, target: converters.GuildorNonGuildUser):
        """Lists warns for a user.

        In order to use this command, You must either have
        Manage Messages permission or a role that
        is assigned as a Helper or above in the bot."""
        await self.get_userlog_embed_for_id(ctx, str(target.id), str(target),
                                            event="warns", guild=ctx.guild)

    @commands.guild_only()
    @commands.command()
    async def mywarns(self, ctx):
        """Lists your warns."""
        await self.get_userlog_embed_for_id(ctx, str(ctx.author.id),
                                            str(ctx.author),
                                            own=True,
                                            event="warns",
                                            guild=ctx.guild)

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command()
    async def clearwarns(self, ctx, *, target: converters.GuildorNonGuildUser):
        """Clears all warns for a user.

        In order to use this command, You must either have
        Administrator permission or a role that
        is assigned as an Admin or above in the bot."""
        msg = await self.clear_event_from_id(str(target.id), "warns", guild=ctx.guild)
        await ctx.send(msg)
        ch = await self.get_mod_config(guild_id=ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format('clearwarns',
                                                         target,
                                                         ctx.author, reason=None)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format('clearwarns',
                                                            target,
                                                            ctx.author, reason=None,
                                                            time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command(aliases=["deletewarn"])
    async def delwarn(self, ctx, target: converters.GuildorNonGuildUser, idx: int):
        """Removes a specific warn from a user.

        In order to use this command, You must either have
        Administrator permission or a role that
        is assigned as an Admin or above in the bot."""
        del_event = await self.delete_event_from_id(str(target.id),
                                                    idx, "warns",
                                                    guild=ctx.guild)
        event_name = "warn"
        # This is hell.
        if isinstance(del_event, discord.Embed):
            await ctx.safe_send(f"{str(target)} has a {event_name} removed!")
            ch = await self.get_mod_config(guild_id=ctx.guild.id)
            if not ch:
                return
            logch = ch.has_log_channel("modlog_chan")
            if logch is not None:
                logch, logstyle = logch
                if logstyle == "kurisu":
                    message = modlog_formatter.kurisu_format('clearwarn',
                                                             target,
                                                             ctx.author, reason=None, warn_number=idx)
                    await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message, embed=del_event)
                if logstyle == "lightning":
                    message = modlog_formatter.lightning_format('clearwarn',
                                                                target,
                                                                ctx.author, reason=None,
                                                                time=ctx.message.created_at,
                                                                warn_count=idx)
                    await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message, embed=del_event)
        else:
            await ctx.send(del_event)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        # Wait for Audit Log to update
        await asyncio.sleep(0.5)
        if not guild.me.guild_permissions.view_audit_log:
            return
        async for entry in guild.audit_logs(limit=50,
                                            action=discord.AuditLogAction.ban):
            # Entry.target = user that was banned fyi
            if entry.target == user:
                author = entry.user
                reason = entry.reason if entry.reason else ""
                #  If author of the entry is the bot itself, don't log since
                #  this would've been already logged.
                if author.id != self.bot.user.id:
                    ch = await self.get_mod_config(guild.id)
                    if not ch:
                        return
                    logch = ch.has_log_channel("modlog_chan")
                    if logch is not None:
                        logch, logstyle = logch
                        if logstyle == "kurisu":
                            message = modlog_formatter.kurisu_format(log_action="Ban",
                                                                     target=entry.target,
                                                                     moderator=author,
                                                                     reason=reason)
                            await self.channelid_send(guild.id, logch, "modlog_chan", message)
                        elif logstyle == "lightning":
                            message = modlog_formatter.lightning_format(log_action="Ban",
                                                                        target=entry.target,
                                                                        moderator=author,
                                                                        reason=reason,
                                                                        time=entry.created_at)
                            await self.channelid_send(guild.id, logch, "modlog_chan", message)
                break

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        # Wait for Audit Log to update
        await asyncio.sleep(0.5)
        if not guild.me.guild_permissions.view_audit_log:
            return
        async for entry in guild.audit_logs(limit=50,
                                            action=discord.AuditLogAction.unban):
            # Entry.target = user that was unbanned fyi
            if entry.target == user:
                author = entry.user
                reason = entry.reason if entry.reason else ""
                if author.id != self.bot.user.id:
                    ch = await self.get_mod_config(guild.id)
                    if ch is None:
                        return
                    logch = ch.has_log_channel("modlog_chan")
                    if logch is not None:
                        logch, logstyle = logch
                        if logstyle == "kurisu":
                            message = modlog_formatter.kurisu_format(log_action="Unban",
                                                                     target=entry.target,
                                                                     moderator=author,
                                                                     reason=reason)
                            await self.channelid_send(guild.id, logch, "modlog_chan", message)
                        elif logstyle == "lightning":
                            message = modlog_formatter.lightning_format(log_action="Unban",
                                                                        target=entry.target,
                                                                        moderator=author,
                                                                        reason=reason,
                                                                        time=entry.created_at)
                            await self.channelid_send(guild.id, logch, "modlog_chan", message)
                break

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.bot.wait_until_ready()
        try:
            query = """SELECT role_id
                    FROM user_restrictions
                    WHERE user_id=$1
                    AND guild_id=$2;
                    """
            rsts = await self.bot.db.fetch(query, member.id, member.guild.id)
            tmp = []
            for r in rsts:
                tmp.append(r[0])
            roles = [discord.utils.get(member.guild.roles, id=rst) for rst in tmp]
            await member.add_roles(*roles, reason="Reapply Role Restrictions")
        except Exception as e:
            self.bot.log.error(e)
            pass
        guild = member.guild
        ch = await self.get_mod_config(guild.id)
        if ch is not None:
            logch = ch.has_log_channel("member_join")
            if logch is not None:
                logch, logstyle = logch
                if logstyle == "kurisu":
                    message = modlog_formatter.kurisu_join_leave("join", member)
                    await self.channelid_send(guild.id, logch, "member_join", message)
                if logstyle == "lightning":
                    message = modlog_formatter.lightning_join_leave("join", member)
                    await self.channelid_send(guild.id, logch, "member_join", message)
        if not member.bot:
            return
        if not guild.me.guild_permissions.view_audit_log:
            # Remove bot add logging since Lightning can't view the audit log
            await self.forbidden_removal("bot_add", guild.id)
            return
        ch = await self.get_mod_config(guild.id)
        if ch is not None:
            logch = ch.has_log_channel("bot_add")
            if logch is not None:
                logch, logstyle = logch
                async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add):
                    if entry.target == member:
                        if logstyle == "kurisu":
                            message = modlog_formatter.kurisu_bot_add(member, entry.user)
                            await self.channelid_send(guild.id, logch, "bot_add", message)
                            break
                        if logstyle == "lightning":
                            message = modlog_formatter.lightning_bot_add(member, entry.user,
                                                                         entry.created_at)
                            await self.channelid_send(guild.id, logch, "bot_add", message)
                            break

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.bot.wait_until_ready()
        guild = member.guild
        ch = await self.get_mod_config(guild.id)
        if ch:
            logch = ch.has_log_channel("member_leave")
            if logch is not None:
                logch, logstyle = logch
                if logstyle == "kurisu":
                    message = modlog_formatter.kurisu_join_leave("leave", member)
                    await self.channelid_send(guild.id, logch, "member_leave", message)
                if logstyle == "lightning":
                    message = modlog_formatter.lightning_join_leave("leave", member)
                    await self.channelid_send(guild.id, logch, "member_leave", message)
        await asyncio.sleep(0.5)
        if not guild.me.guild_permissions.view_audit_log:
            return
        async for entry in guild.audit_logs(action=discord.AuditLogAction.kick,
                                            limit=50):
            if entry.target == member:
                if member.joined_at is None or member.joined_at > entry.created_at \
                        or entry.created_at < datetime.utcfromtimestamp(
                        time.time() - 10):
                    break
                author = entry.user
                reason = entry.reason if entry.reason else ""
                if author.id != self.bot.user.id:
                    ch = await self.get_mod_config(guild.id)
                    if not ch:
                        return
                    logch = ch.has_log_channel("modlog_chan")
                    if logch is not None:
                        logch, logstyle = logch
                        if logstyle == "kurisu":
                            message = modlog_formatter.kurisu_format(log_action="Kick",
                                                                     target=entry.target,
                                                                     moderator=author,
                                                                     reason=reason)
                            await self.channelid_send(guild.id, logch, "modlog_chan", message)
                        elif ch['log_format'] == "lightning":
                            message = modlog_formatter.lightning_format(log_action="Kick",
                                                                        target=entry.target,
                                                                        moderator=author,
                                                                        reason=reason,
                                                                        time=entry.created_at)
                            await self.channelid_send(guild.id, logch, "modlog_chan", message)
                break

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        await self.bot.wait_until_ready()
        if before.roles != after.roles:
            await asyncio.sleep(0.5)
            if not before.guild.me.guild_permissions.view_audit_log:
                return
            ch = await self.get_mod_config(after.guild.id)
            if not ch:
                return
            logch = ch.has_log_channel("role_change")
            if logch:
                logch, logstyle = logch
                if logstyle == "kurisu":
                    added = [role for role in after.roles if role not in before.roles]
                    removed = [role for role in before.roles if role not in after.roles]
                    async for entry in before.guild.audit_logs(action=discord.AuditLogAction.member_role_update,
                                                               limit=50):
                        if entry.target == after and all(role in entry.changes.after.roles for role in added) \
                                and all(role in entry.changes.before.roles for role in removed):
                            msg = modlog_formatter.kurisu_role_change(added, removed, after, entry.user)
                            await self.channelid_send(after.guild.id, logch, "role_change", msg)
                            break
                if logstyle == "lightning":
                    added = [role for role in after.roles if role not in before.roles]
                    removed = [role for role in before.roles if role not in after.roles]
                    async for entry in before.guild.audit_logs(action=discord.AuditLogAction.member_role_update,
                                                               limit=50):
                        if entry.target == after and all(role in entry.changes.after.roles for role in added) \
                                and all(role in entry.changes.before.roles for role in removed):
                            msg = modlog_formatter.lightning_role_change(after, added, removed, entry.user,
                                                                         entry.created_at, entry.reason)
                            await self.channelid_send(after.guild.id, logch, "role_change", msg)
                            break


def setup(bot):
    bot.add_cog(Mod(bot))
