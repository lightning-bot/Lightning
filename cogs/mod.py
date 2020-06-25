# Lightning.py - A multi-purpose Discord bot
# Copyright (C) 2020 - LightSage
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

import asyncio
import io
import json
import time
from datetime import datetime, timedelta
from collections import Counter

import asyncpg
import dateutil.parser
import discord
from discord.ext import commands

from utils import converters, modlog_formatter, cache, flags, paginator
from utils.checks import is_staff_or_has_perms, is_staff_or_has_channel_perms
from utils.database import GuildModConfig
from utils.errors import MuteRoleError, TimersUnavailable, WarnError, LightningError
from utils.time import FutureTime, natural_timedelta, plural, get_utc_timestamp
from resources import botemojis


class WarnPages(paginator.Pages):
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


class NoReason(commands.CustomDefault):
    """CustomDefault for BoolFlags that only use --no-dm"""
    async def default(self, ctx, param):
        return {'--no-dm': False, 'text': ''}


class Mod(commands.Cog):
    """
    Moderation and server management commands.
    """
    def __init__(self, bot):
        self.bot = bot

    def __repr__(self):
        return '<cogs.Mod>'

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @cache.cache(maxsize=32, strategy=cache.Strategy.lru)
    async def get_mod_config(self, guild_id):
        """
        Returns: :class: `GuildModConfig` if guild_id is in the database,
        else returns None
        """
        query = """SELECT * FROM guild_mod_config WHERE guild_id=$1"""
        async with self.bot.db.acquire() as con:
            record = await con.fetchrow(query, guild_id)
        if not record:
            return None
        return GuildModConfig(record)

    def mod_reason(self, ctx, reason: str):
        if reason:
            to_return = f"{ctx.author} (ID: {ctx.author.id}): {reason}"
        else:
            to_return = f"Action done by {ctx.author} (ID: {ctx.author.id})"
        if len(to_return) > 512:
            raise commands.BadArgument('Reason is too long!')
        return to_return

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
                   VALUES ($1, $2, $3) ON CONFLICT DO NOTHING;
                """
        return await self.bot.db.execute(query, guild_id, user_id, role_id)

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
    async def kick(self, ctx, target: converters.TargetMember,
                   *, reason: flags.BoolFlags(['--no-dm'],
                                              raise_errors=False,
                                              flag_aliases={'--nodm': '--no-dm'})
                   = NoReason):
        """Kicks a user.

        Flag options (no arguments):
        `--no-dm` or `--nodm`: Bot does not DM the user the reason for the action.

        In order to use this command, you must either have
        Kick Members permission or a role that
        is assigned as a Moderator or above in the bot."""
        pflags = reason
        if pflags['--no-dm'] is False:
            dm_message = f"You were kicked from {ctx.guild.name}."
            if pflags['text']:
                dm_message += f" The given reason is: \"{pflags['text']}\"."

            try:
                await target.send(dm_message)
            except (AttributeError, discord.errors.Forbidden):
                pass

        await ctx.guild.kick(target, reason=f"{self.mod_reason(ctx, pflags['text'])}")
        await ctx.safe_send(f"{target} has been kicked. 👌 ")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="kick", target=target,
                                                         moderator=ctx.author, reason=pflags['text'])
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("kick", target, ctx.author,
                                                            reason=pflags['text'],
                                                            time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()  # This isn't needed but w/e :shrugkitty:
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    @commands.command()
    async def ban(self, ctx, target: converters.TargetNonGuildMember,
                  *, reason: flags.BoolFlags(['--no-dm'],
                                             raise_errors=False,
                                             flag_aliases={'--nodm': '--no-dm'})
                  = NoReason):
        """Bans a user.

        Flag options (no arguments):
        `--no-dm` or `--nodm`: Bot does not DM the user the reason for the action.

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""
        pflags = reason
        if pflags['--no-dm'] is False:
            dm_message = f"You were banned from {ctx.guild.name}."
            if reason:
                dm_message += f" The given reason is: \"{pflags['text']}\"."
            dm_message += "\n\nThis ban does not expire."
            dm_message += "\n\nIf you believe this to be in error, please message the staff."

            try:
                await target.send(dm_message)
            except (AttributeError, discord.errors.Forbidden):
                pass

        await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, pflags['text'])}",
                            delete_message_days=0)
        await ctx.safe_send(f"{target} is now b&. 👍")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="ban", target=target,
                                                         moderator=ctx.author, reason=pflags['text'])
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("ban", target, ctx.author,
                                                            reason=pflags['text'],
                                                            time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    async def warn_user(self, ctx, target, reason: str = ""):
        query = """INSERT INTO warns (guild_id, user_id, mod_id, timestamp, reason)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING warn_id, (SELECT COUNT(*) FROM warns
                                       WHERE guild_id=$1 AND user_id=$2 AND pardoned='0')
                """
        if not reason:
            reason = "No reason provided."
        return await self.bot.db.fetchrow(query, ctx.guild.id, target.id,
                                          ctx.author.id, ctx.message.created_at,
                                          reason)

    async def warn_count_check(self, ctx, warn_count, target, reason: str = "", no_dm=False):
        msg = f"You were warned in {ctx.guild.name}."
        if reason:
            msg += " The given reason is: " + reason
        msg += f"\n\nThis is warn #{warn_count}."
        punishable_warn = await self.get_mod_config(ctx.guild.id)
        if not punishable_warn:
            if isinstance(target, discord.Member):
                if no_dm is True:
                    return warn_count
                try:
                    await target.send(msg)
                    return warn_count
                except (AttributeError, discord.errors.Forbidden):
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
            if no_dm is False:
                try:
                    await target.send(msg)
                except (AttributeError, discord.errors.Forbidden):
                    pass
            if punishable_warn.warn_kick:
                if warn_count == punishable_warn.warn_kick:
                    opt_reason = f"[AutoMod] Reached {warn_count} warns. "
                    try:
                        await ctx.guild.kick(target,
                                             reason=f"{self.mod_reason(ctx, opt_reason)}")
                    except discord.Forbidden:
                        return warn_count
                    self.bot.dispatch("automod_action", ctx.guild, "kick", target, opt_reason)
        if punishable_warn.warn_ban:
            if warn_count >= punishable_warn.warn_ban:  # just in case
                opt_reason = f"[AutoMod] Exceeded WarnBan Limit ({warn_count}). "
                try:
                    await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, opt_reason)}",
                                        delete_message_days=0)
                except discord.Forbidden:
                    return warn_count
                self.bot.dispatch("automod_action", ctx.guild, "ban", target, opt_reason)
        return warn_count

    @commands.guild_only()
    @is_staff_or_has_perms("Helper", manage_messages=True)
    @commands.group(invoke_without_command=True)
    async def warn(self, ctx, target: converters.TargetMember,
                   *, reason: flags.BoolFlags(['--no-dm'],
                                              raise_errors=False,
                                              flag_aliases={'--nodm': '--no-dm'})
                   = NoReason):
        """Warns a user.

        Flag options (no arguments):
        `--no-dm` or `--nodm`: Bot does not DM the user the reason for the action.

        In order to use this command, you must either have
        Manage Messages permission or a role
        that is assigned as a Helper or above in the bot."""
        warn_reason = reason['text']
        no_dm = reason['--no-dm']
        warns = await self.warn_user(ctx, target, warn_reason)
        warn_count = await self.warn_count_check(ctx, warns['count'] + 1, target,
                                                 warn_reason, no_dm)
        await ctx.safe_send(f"{target} warned. (Warn ID: {warns['warn_id']}) "
                            f"User now has {plural(warn_count):warning}.")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="warn", target=target,
                                                         moderator=ctx.author,
                                                         reason=warn_reason,
                                                         warn_id=warns['warn_id'])
                await self.channelid_send(ctx.guild.id, int(logch), "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("warn", target, ctx.author,
                                                            reason=warn_reason,
                                                            time=ctx.message.created_at,
                                                            warn_id=warns['warn_id'])
                await self.channelid_send(ctx.guild.id, int(logch), "modlog_chan", message)

    @warn.command(name="transfer")
    @commands.cooldown(rate=1, per=30.0, type=commands.BucketType.guild)
    @is_staff_or_has_perms("Admin", manage_guild=True)
    async def warn_transfer(self, ctx, old_user: discord.Member, new_user: discord.Member):
        """Transfers warnings to another member.

        You must have both members in the server to transfer warnings.

        In order to use this command, you must either have
        Manage Server permission or a role
        that is assigned as an Administrator in the bot."""
        warns = await self.transfer_warns_to_id(ctx.guild.id, old_user.id, new_user.id)
        if len(warns) == 0:
            return await ctx.safe_send(f"{str(old_user)} does not have any warnings!")
        await ctx.safe_send(f"\U0001f44c Transferred {plural(len(warns)):warning} to {str(new_user)}")

    @commands.guild_only()
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
    @commands.bot_has_permissions(kick_members=True)
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
    @commands.bot_has_permissions(ban_members=True)
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

    async def do_message_purge(self, ctx, limit, predicate, *, before=None, after=None):
        if limit > 150:
            return await ctx.send("You can only purge 150 messages at a time!")
        if before is None:
            before = ctx.message
        else:
            before = discord.Object(id=before)
        if after is not None:
            after = discord.Object(id=after)
        try:
            purged = await ctx.channel.purge(limit=limit, before=before, after=after, check=predicate)
        except discord.Forbidden:
            raise commands.MissingPermissions(['manage_messages'])
        except discord.HTTPException as e:
            raise LightningError(f"Error: {e} (try a smaller message search?)")
        spam = Counter(str(m.author) for m in purged)
        dcount = len(purged)
        messages = [f"**{plural(dcount):message} purged**"]
        if dcount:
            messages.append('')
            spam = sorted(spam.items(), key=lambda m: m[1], reverse=True)
            messages.extend(f'{name}: {count}' for name, count in spam)
        msg = '\n'.join(messages)
        if len(messages) > 2000:
            # Cool.
            await ctx.send(f"Purged {plural(dcount):message}.")
        else:
            await ctx.safe_send(msg)

    @commands.bot_has_permissions(manage_messages=True)
    @is_staff_or_has_channel_perms("Moderator", manage_messages=True)
    @commands.group(invoke_without_command=True)
    async def purge(self, ctx, search: int):
        """Purges messages that meet a certain criteria.

        If called without a subcommand, the bot will remove all messages.

        In order to use this command, you must either have
        Manage Messages permission or a role that
        is assigned as a Moderator or above in the bot."""
        await self.do_message_purge(ctx, search, lambda m: True)

    @purge.error
    async def purge_error(self, ctx, error):
        if isinstance(error, LightningError):
            return await ctx.safe_send(error)
        elif isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send("You need to provide a number of messages to search!")
        elif isinstance(error, commands.BotMissingPermissions):
            p = ', '.join(error.missing_perms).replace('_', ' ').replace('guild', 'server').title()
            return await ctx.send("I don't have "
                                  "the right permissions to run this command. "
                                  f"Please add the following permissions to me: {p}")
        elif isinstance(error, commands.MissingPermissions):
            p = ', '.join(error.missing_perms).replace('_', ' ').replace('guild', 'server').title()
            return await ctx.send("You don't have "
                                  f"the right permissions to run this command. You need {p}.")

    @commands.bot_has_permissions(manage_messages=True)
    @is_staff_or_has_channel_perms("Moderator", manage_messages=True)
    @purge.command(name="user")
    async def purge_from_user(self, ctx, member: discord.Member, search: int = 100):
        """Removes messages from a member"""
        await self.do_message_purge(ctx, search, lambda m: m.author == member)

    @commands.bot_has_permissions(manage_messages=True)
    @is_staff_or_has_channel_perms("Moderator", manage_messages=True)
    @purge.command(name="attachments", aliases=['files'])
    async def purge_files(self, ctx, search: int = 100):
        """Removes messages that contains attachments in the message."""
        await self.do_message_purge(ctx, search, lambda e: len(e.attachments))

    @commands.bot_has_permissions(manage_messages=True)
    @is_staff_or_has_channel_perms("Moderator", manage_messages=True)
    @purge.command()
    async def contains(self, ctx, *, string: str):
        """Removes messages containing a certain substring."""
        if len(string) < 5:
            raise LightningError("The string length must be at least 5 characters!")
        else:
            await self.do_message_purge(ctx, 100, lambda e: string in e.content)

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
    async def mute(self, ctx, target: converters.TargetMember,
                   *, reason: flags.BoolFlags(['--no-dm'],
                                              raise_errors=False,
                                              flag_aliases={'--nodm': '--no-dm'})
                   = NoReason):
        """Mutes a user.

        Flag options (no arguments):
        `--no-dm` or `--nodm`: Bot does not DM the user the reason for the action.

        In order to use this command, you must either have
        Manage Roles permission or a role that
        is assigned as a Moderator or above in the bot."""
        role = await self.get_mute_role(ctx)
        pflags = reason
        if pflags['--no-dm'] is False:
            dm_message = f"You were muted in {ctx.guild.name}!"
            if pflags['text']:
                dm_message += f" The given reason is: \"{pflags['text']}\"."
            try:
                await target.send(dm_message)
            except (AttributeError, discord.errors.Forbidden):
                # rip
                pass
        await target.add_roles(role, reason=f"{self.mod_reason(ctx, '[Mute]')}")
        await self.set_user_restrictions(ctx.guild.id, target.id, role.id)
        await ctx.safe_send(f"{target} can no longer speak.")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="mute", target=target,
                                                         moderator=ctx.author, reason=pflags['text'])
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("mute", target,
                                                            ctx.author,
                                                            reason=pflags['text'],
                                                            time=ctx.message.created_at)
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
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="unmute", target=target,
                                                         moderator=ctx.author, reason=reason)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
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
        await ctx.safe_send(f"\U0001f44c {target.user} is now unbanned.")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="unban", target=target.user,
                                                         moderator=ctx.author, reason=reason)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("unban", target.user, ctx.author,
                                                            reason=reason, time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    @commands.command(aliases=['tempban'])
    async def timeban(self, ctx, target: converters.TargetNonGuildMember,
                      duration: FutureTime,
                      *, reason: flags.BoolFlags(['--no-dm'],
                                                 raise_errors=False,
                                                 flag_aliases={'--nodm': '--no-dm'})
                      = NoReason):
        """Bans a user for a specified amount of time.

        The duration can be a short time format such as "30d",
        a more human duration format such as "until Monday at 7PM",
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC.

        Flag options (no arguments):
        `--no-dm` or `--nodm`: Bot does not DM the user the reason for the action.

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
        pflags = reason
        if pflags['--no-dm'] is False:
            if isinstance(target, (discord.Member, discord.User)):
                dm_message = f"You were banned from {ctx.guild.name}."
                if pflags['text']:
                    dm_message += f" The given reason is: \"{pflags['text']}\"."
                dm_message += f"\n\nThis ban will expire in {duration_text}."
                try:
                    await target.send(dm_message)
                except (AttributeError, discord.errors.Forbidden):
                    pass
        if pflags['text']:
            opt_reason = f"{pflags['text']} (Timeban expires in {duration_text})"
        else:
            opt_reason = f" (Timeban expires in {duration_text})"
        await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, opt_reason)}",
                            delete_message_days=0)
        await ctx.safe_send(f"{str(target)} is now b&. 👍 "
                            f"It will expire in {duration_text}.")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format("timeban", target,
                                                         ctx.author, pflags['text'],
                                                         expiry=duration_text)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("timeban", target, ctx.author,
                                                            reason=pflags['text'],
                                                            time=ctx.message.created_at,
                                                            expiry=duration_text)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @commands.guild_only()
    @commands.command(aliases=['tempmute'])
    @commands.bot_has_permissions(manage_roles=True)
    @is_staff_or_has_perms("Moderator", manage_roles=True)
    async def timemute(self, ctx, target: converters.TargetMember,
                       duration: FutureTime,
                       *, reason: flags.BoolFlags(['--no-dm'],
                                                  raise_errors=False,
                                                  flag_aliases={'--nodm': '--no-dm'})
                       = NoReason):
        """Mutes a user for a specified amount of time.

        The duration can be a short time format such as "30d",
        a more human duration format such as "until Monday at 7PM",
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC.

        Flag options (no arguments):
        `--no-dm` or `--nodm`: Bot does not DM the user the reason for the action.

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
        pflags = reason
        if pflags['--no-dm'] is False:
            dm_message = f"You were muted in {ctx.guild.name}!"
            if pflags['text']:
                dm_message += f" The given reason is: \"{pflags['text']}\"."
            dm_message += f"\n\nThis mute will expire in {duration_text}."
            try:
                await target.send(dm_message)
            except (AttributeError, discord.errors.Forbidden):
                pass
        if pflags['text']:
            opt_reason = f"{pflags['text']} (Timemute expires in {duration_text})"
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
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format(log_action="timemute", target=target,
                                                         moderator=ctx.author,
                                                         reason=pflags['text'],
                                                         expiry=duration_text)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format("timemute", target, ctx.author,
                                                            reason=pflags['text'],
                                                            time=ctx.message.created_at,
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
        if role > ctx.author.top_role:
            return await ctx.send('That role is higher than your highest role.')
        if role > ctx.me.top_role:
            return await ctx.send('That role is higher than my highest role.')
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
        ch = await self.get_mod_config(ctx.guild.id)
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

    @commands.bot_has_permissions(manage_channels=True)
    @is_staff_or_has_perms("Moderator", manage_channels=True)
    @commands.group(aliases=['lockdown'], invoke_without_command=True)
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

        await channel.set_permissions(ctx.guild.default_role, send_messages=False,
                                      add_reactions=False)
        await channel.set_permissions(ctx.me, send_messages=True, manage_channels=True)
        await ctx.send(f"🔒 {channel.mention} is now locked.")
        ch = await self.get_mod_config(ctx.guild.id)
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

    @commands.bot_has_permissions(manage_channels=True)
    @is_staff_or_has_perms("Admin", manage_channels=True)
    @lock.command(name="hard")
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
                           f"Use `{ctx.prefix}unlock hard` to unlock the channel.")
            return

        await channel.set_permissions(ctx.guild.default_role, read_messages=False,
                                      send_messages=False)
        await channel.set_permissions(ctx.me, read_messages=True,
                                      send_messages=True, manage_channels=True)
        await ctx.send(f"🔒 {channel.mention} is now hard locked.")
        ch = await self.get_mod_config(ctx.guild.id)
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
    @commands.group(invoke_without_command=True)
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
        ch = await self.get_mod_config(ctx.guild.id)
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

    @commands.bot_has_permissions(manage_channels=True)
    @is_staff_or_has_perms("Admin", manage_channels=True)
    @unlock.command(name='hard')
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

        await channel.set_permissions(ctx.guild.default_role,
                                      read_messages=None, send_messages=None)
        await ctx.send(f"🔓 {channel.mention} is now unlocked.")
        ch = await self.get_mod_config(ctx.guild.id)
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
        ch = await self.get_mod_config(guild.id)
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
            ch = await self.get_mod_config(guild.id)
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
        ch = await self.get_mod_config(guild.id)
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

    async def get_warns_for_id(self, ctx, user_id: int, author_warns: bool = True,
                               name: str = ""):
        query = """SELECT wa.warn_id, wa.reason, wa.timestamp,
                   wa.mod_id, p.mod_id AS pardon_mod_id,
                   p.timestamp AS pardon_timestamp
                   FROM warns wa
                   LEFT JOIN pardoned_warns p ON wa.warn_id = p.warn_id
                   WHERE wa.guild_id=$1
                   AND wa.user_id=$2
                   ORDER BY wa.warn_id ASC
                """
        ret = await self.bot.db.fetch(query, ctx.guild.id, user_id)
        if len(ret) == 0:
            return await ctx.safe_send(f"{name if name else user_id} has no warnings!")
        warnings = []

        for w in ret:
            if author_warns is False:
                moderator = ctx.guild.get_member(w['mod_id'])
                if moderator:
                    moderator = f": {moderator} ({moderator.id})"
                else:
                    moderator = f" ID: {w['mod_id']}"
                moderator_text = f"Moderator{moderator}"
            else:
                moderator_text = ""
            if w['pardon_mod_id']:
                pmod = ctx.guild.get_member(w['pardon_mod_id'])
                if pmod:
                    pmod = f"{pmod} ({pmod.id})"
                else:
                    pmod = f"Mod ID: {w['pardon_mod_id']}"
                pardon = f"\n**Pardoned Warn by: {pmod} at "\
                         f"{get_utc_timestamp(w['pardon_timestamp'])}**"
            else:
                pardon = ""
            warnings.append((f"Warn ID **{w['warn_id']}**: {get_utc_timestamp(w['timestamp'])}",
                             f"{moderator_text if moderator_text else ''}\nReason: "
                             f"{w['reason']}" + pardon))
        if name:
            name = f"{name} ({user_id})"
        else:
            name = f"ID: {user_id}"
        p = WarnPages(f"Warns for {name}", ctx, entries=warnings, per_page=5)
        p.embed.color = 0xf51515
        return await p.paginate()

    async def pardon_warn(self, ctx, warn_id: int):
        query = """INSERT INTO pardoned_warns (guild_id, warn_id, mod_id, timestamp)
                   VALUES ($1, $2, $3, $4);
                """
        query2 = """UPDATE warns
                    SET pardoned = '1'
                    WHERE guild_id=$1 AND warn_id=$2
                    RETURNING user_id
                 """
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                try:
                    await con.execute(query, ctx.guild.id, warn_id, ctx.author.id,
                                      ctx.message.created_at)
                except asyncpg.UniqueViolationError:
                    raise WarnError(f"Warn ID: `{warn_id}` is already pardoned.")
                except asyncpg.ForeignKeyViolationError:
                    raise WarnError(f"{botemojis.x} That warn ID does not exist!")
                return await con.fetchrow(query2, ctx.guild.id, warn_id)

    async def transfer_warns_to_id(self, guild_id: int, previous_user: int, new_user: int):
        """Transfers warns to another ID"""
        query = """UPDATE warns
                   SET user_id = $1
                   WHERE guild_id=$2 AND user_id = $3
                   RETURNING warn_id;
                """
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                return await con.fetch(query, new_user, guild_id, previous_user)

    async def clear_warns_by_id(self, guild_id: int, user_id: int, name: str = ""):
        """Clears warns for a user id.

        Parameters
        -----------
        guild_id: int
            The guild ID you are clearing the warnings from.
        user_id: int
            The user ID that you are clearing all warnings from.
        name: str
            Optional string of the name of the user whose warnings are being cleared.

        Returns
        --------
        :class:discord.File containing all warns cleared and a count of
        how many warnings were cleared."""
        warnlist = """SELECT warn_id, reason, timestamp, mod_id, pardoned FROM warns
                      WHERE guild_id=$1
                      AND user_id=$2
                      ORDER BY warn_id ASC;
                   """
        query = """DELETE FROM warns
                   WHERE guild_id=$1
                   AND user_id=$2
                """
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                warnlist = await con.fetch(warnlist, guild_id, user_id)
                if not warnlist:
                    raise WarnError(f"{name if name else user_id} has no warnings!")
                await con.execute(query, guild_id, user_id)
        # Prepare a warn file
        clearedwarns = []
        for warn in warnlist:
            clearedwarns.append(warn['warn_id'])
            clearedwarns.append(get_utc_timestamp(warn['timestamp']))
            clearedwarns.append(warn['mod_id'])
            clearedwarns.append(warn['reason'] if warn['reason'] else "No reason provided")
        text = self.make_markdown_formatted_table(['Warn ID', 'Timestamp', 'Moderator ID', 'Reason'], clearedwarns)
        file = io.StringIO()
        file.write(text)
        file.seek(0)
        return discord.File(file, filename=f"cleared_warn_list_{user_id}.md"), len(clearedwarns) // 4

    def make_markdown_formatted_table(self, columns: list, data: list):
        """Makes a table in Github flavored markdown"""
        table = ""
        for c in columns:
            table += "|{:^{table}}".format(c, table=(len(c) + 2))
        table += "|\n"
        table += f"| --- " * len(columns)
        table += "|\n"
        counter = 0
        for d in data:
            if counter >= len(columns):
                table += f"|\n"
                # Reset our counter
                counter = 0
            table += f"| {d} "
            counter += 1
        table += "|\n"
        return table

    async def delete_warn_by_id(self, ctx, guild_id: int, warn_id: int, uid: int = None) -> discord.Embed:
        """Deletes a warn by Warn ID.

        Parameters
        -----------
        ctx: Context
            The context of the command.
        guild_id: int
            The guild id that you are deleting a warn from.
        warn_id: int
            The warning ID of the warning you are deleting.
        uid: int
            An optional extra lookup for the warning ID.
            Default: None

        Returns
        -------
        :class:discord.Embed containing information about the warning that was deleted"""
        if uid is None:
            query1 = """SELECT reason, mod_id, timestamp, user_id FROM warns
                        WHERE guild_id=$1
                        AND warn_id=$2;
                    """
        else:
            query1 = """SELECT reason, mod_id, timestamp, user_id FROM warns
                        WHERE guild_id=$1
                        AND warn_id=$2 AND user_id=$3;
                    """
        query2 = """DELETE FROM warns
                    WHERE guild_id=$1
                    AND warn_id=$2;
                """
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                if uid is None:
                    entry = await con.fetchrow(query1, guild_id, warn_id)
                else:
                    entry = await con.fetchrow(query1, guild_id, warn_id, uid)
                if entry is None:
                    raise WarnError(f"Warn ID \"{warn_id}\" does not exist!")
                await con.execute(query2, guild_id, warn_id)
        msg = ""
        user = ctx.guild.get_member(entry['user_id'])
        if user:
            msg += f"User: {user} ({user.id})\n"
        else:
            msg += f"User ID: {entry['user_id']}"
        moderator = ctx.guild.get_member(entry['mod_id'])
        if moderator:
            msg += f"Moderator: {moderator} ({moderator.id})\n"
        else:
            msg += f"Moderator ID: {entry['mod_id']}\n"
        msg += f"Timestamp: {get_utc_timestamp(entry['timestamp'])}\nReason: {entry['reason']}"
        em = discord.Embed(title="Deleted Warn", color=0xf51515,
                           description=msg, timestamp=ctx.message.created_at)
        return em

    @is_staff_or_has_perms("Helper", manage_messages=True)
    @commands.command()
    @commands.cooldown(1, 10.0, commands.BucketType.member)  # Lol
    async def listwarns(self, ctx, *, target: converters.GuildorNonGuildUser):
        """Lists warns for a user.

        In order to use this command, you must either have
        Manage Messages permission or a role that
        is assigned as a Helper or above in the bot."""
        await self.get_warns_for_id(ctx, target.id, author_warns=False, name=target)

    @commands.command()
    async def mywarns(self, ctx):
        """Lists your warns."""
        await self.get_warns_for_id(ctx, ctx.author.id, author_warns=True, name=str(ctx.author))

    @commands.command(usage="<warn ID>")
    @is_staff_or_has_perms("Moderator", manage_messages=True)
    async def pardonwarn(self, ctx, warn_id: int):
        """Pardons a warning by warn ID.

        This transforms a warn into a "softwarn".

        In order to use this command, you must either have
        Manage Messages permission or a role that is assigned
        as a Moderator in the bot."""
        value = await self.pardon_warn(ctx, warn_id)
        member = ctx.guild.get_member(value['user_id'])
        if not member:
            member = discord.Object(id=value['user_id'])
        await ctx.send(f"\N{OK HAND SIGN} Pardoned warn `{warn_id}`")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format('pardonwarn',
                                                         member,
                                                         ctx.author, reason=None, warn_id=warn_id)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format('pardonwarn',
                                                            member,
                                                            ctx.author, reason=None,
                                                            time=ctx.message.created_at, warn_id=warn_id)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message)

    @pardonwarn.error
    async def pdw_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"{botemojis.x} You need to provide a warn ID to pardon.")
        elif isinstance(error, commands.BadArgument):
            return await ctx.send(f"{botemojis.x} You need to provide a warn ID.")
        elif isinstance(error, LightningError):
            return await ctx.safe_send(error)

    async def get_old_userlog(self, guild):
        query = """SELECT userlog FROM userlogs WHERE guild_id=$1"""
        ret = await self.bot.db.fetchval(query, guild.id)
        if ret:
            return json.loads(ret)
        else:
            return {}

    @commands.command()
    @is_staff_or_has_perms("Admin", manage_guild=True)
    @commands.cooldown(1, 60.0, commands.BucketType.guild)
    async def migratewarns(self, ctx):
        """Migrates the server's warnings to the new warn system."""
        userlog = await self.get_old_userlog(ctx.guild)
        if len(userlog) == 0:
            return await ctx.send("This server has no warns recorded for any users "
                                  "or you have already migrated warns.")
        entries = []
        for uid in userlog:
            if userlog[uid]['warns']:
                for idx, entry in enumerate(userlog[uid]['warns']):
                    toadd = {"guild_id": ctx.guild.id,
                             "user_id": int(uid),
                             "mod_id": entry['issuer_id'],
                             "timestamp": dateutil.parser.parse(entry['timestamp'][:-4]).isoformat(),
                             "reason": entry['reason'] if entry['reason'] else "No reason provided."}
                    entries.append(toadd)
        query = """INSERT INTO warns (guild_id, user_id, mod_id, timestamp, reason)
                   SELECT data.guild_id, data.user_id, data.mod_id, data.timestamp, data.reason
                   FROM jsonb_to_recordset($1::jsonb) AS
                   data(guild_id BIGINT, user_id BIGINT, mod_id BIGINT,
                        timestamp TIMESTAMP, reason TEXT)
                """
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute(query, json.dumps(entries))
                query = """DELETE FROM userlogs WHERE guild_id=$1"""
                await con.execute(query, ctx.guild.id)
        await ctx.send(f"\N{OK HAND SIGN} Migrated {len(entries)} warn entries.")

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command()
    @commands.cooldown(1, 30.0, commands.BucketType.guild)
    async def clearwarns(self, ctx, *, target: converters.GuildorNonGuildUser):
        """Clears all warns for a user.

        In order to use this command, You must either have
        Administrator permission or a role that
        is assigned as an Admin or above in the bot."""
        fattachment, warncount = await self.clear_warns_by_id(ctx.guild.id, target.id, str(target))
        await ctx.safe_send(f"\N{OK HAND SIGN} Cleared {warncount} warnings from {target}")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_format('clearwarns',
                                                         target,
                                                         ctx.author, reason=None)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message, file=fattachment)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_format('clearwarns',
                                                            target,
                                                            ctx.author, reason=None,
                                                            time=ctx.message.created_at)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message, file=fattachment)

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command(aliases=["deletewarn"], usage="<warn ID> [user]")
    async def delwarn(self, ctx, warn_id: int, *, target: discord.Member = None):
        """Removes a specific warn ID.

        In order to use this command, you must either have
        Administrator permission or a role that
        is assigned as an Admin or above in the bot."""
        if target is None:
            em = await self.delete_warn_by_id(ctx, ctx.guild.id, warn_id)
        else:
            em = await self.delete_warn_by_id(ctx, ctx.guild.id, warn_id, target.id)
        if target is None:
            await ctx.safe_send(f"\N{OK HAND SIGN} Deleted warn ID `{warn_id}`")
        else:
            await ctx.safe_send(f"\N{OK HAND SIGN} Deleted warn ID `{warn_id}` from {str(target)}")
        ch = await self.get_mod_config(ctx.guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            logch, logstyle = logch
            if logstyle == "kurisu":
                message = modlog_formatter.kurisu_remove_warn_id(ctx.author,
                                                                 warn_id, member=target)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message, embed=em)
            if logstyle == "lightning":
                message = modlog_formatter.lightning_remove_warn_id(ctx.author,
                                                                    warn_id, ctx.message.created_at,
                                                                    member=target)
                await self.channelid_send(ctx.guild.id, logch, "modlog_chan", message, embed=em)

    @commands.Cog.listener()
    async def on_automod_action(self, guild, action, user, reason):
        await self.bot.wait_until_ready()
        ch = await self.get_mod_config(guild.id)
        if not ch:
            return
        logch = ch.has_log_channel("modlog_chan")
        if logch is not None:
            if logch[1] == "kurisu":
                message = modlog_formatter.kurisu_format(action, user, self.bot.user, reason)
                await self.channelid_send(guild.id, logch[0], "modlog_chan", message)
            if logch[1] == "lightning":
                message = modlog_formatter.lightning_format(action, user, self.bot.user, reason)
                await self.channelid_send(guild.id, logch[0], "modlog_chan", message)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.bot.wait_until_ready()
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
                        elif logstyle == "lightning":
                            message = modlog_formatter.lightning_format(log_action="Kick",
                                                                        target=entry.target,
                                                                        moderator=author,
                                                                        reason=reason,
                                                                        time=entry.created_at)
                            await self.channelid_send(guild.id, logch, "modlog_chan", message)
                break

    async def find_occurance(self, guild, action, match, limit=50, retry=True):
        if hasattr(guild, 'me') is False:
            return None
        entry = None
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for e in guild.audit_logs(action=action, limit=limit):
                    if match(e):
                        if entry is None or e.id > entry.id:
                            entry = e
            except discord.Forbidden:
                pass
        if entry is None and retry:
            await asyncio.sleep(2)
            return await self.find_occurance(guild, action, match, limit, False)
        # if entry is not None and isinstance(entry.target, discord.Object):
        #    entry.target = await self.bot.get_user(entry.target.id)
        return entry

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        await self.bot.wait_until_ready()
        guild = before.guild
        if before.roles != after.roles:
            ch = await self.get_mod_config(after.guild.id)
            if not ch:
                return
            logch = ch.has_log_channel("role_change")
            if logch:
                logch, logstyle = logch
                added = [role for role in after.roles if role not in before.roles]
                removed = [role for role in before.roles if role not in after.roles]
                if (len(added) + len(removed)) == 0:
                    return

                def etc(entry):
                    e = entry
                    if entry.target.id == before.id and hasattr(e.changes.before, "roles") \
                        and hasattr(e.changes.after, "roles") and \
                        all(r in e.changes.before.roles for r in removed) and \
                            all(r in e.changes.after.roles for r in added):
                        return True
                    return False
                entry = await self.find_occurance(guild, discord.AuditLogAction.member_role_update,
                                                  etc)
                if logstyle == "kurisu":
                    if entry:
                        removed = entry.changes.before.roles
                        added = entry.changes.after.roles
                        msg = modlog_formatter.kurisu_role_change(added, removed, after, entry.user)
                    else:
                        msg = modlog_formatter.kurisu_role_change(added, removed, after)
                    await self.channelid_send(after.guild.id, logch, "role_change", msg)
                if logstyle == "lightning":
                    if entry:
                        removed = entry.changes.before.roles
                        added = entry.changes.after.roles
                        msg = modlog_formatter.lightning_role_change(after, added, removed, entry.user,
                                                                     entry.created_at, entry.reason)
                    else:
                        msg = modlog_formatter.lightning_role_change(after, added, removed, None,
                                                                     datetime.utcnow())
                    await self.channelid_send(after.guild.id, logch, "role_change", msg)


def setup(bot):
    bot.add_cog(Mod(bot))
