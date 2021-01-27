"""
Lightning.py - A personal Discord bot
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
import asyncio
from collections import Counter
from datetime import datetime, timedelta
from typing import Union

import discord
from discord.ext import commands

from lightning import (CommandLevel, LightningCog, LightningContext, cache,
                       command, converters)
from lightning import flags as dflags
from lightning import group
from lightning.errors import LightningError, MuteRoleError, TimersUnavailable
from lightning.formatters import truncate_text
from lightning.models import Action, GuildModConfig, LoggingConfig
from lightning.utils import helpers, modlogformats
from lightning.utils.checks import (has_channel_permissions,
                                    has_guild_permissions)
from lightning.utils.time import (FutureTime, get_utc_timestamp,
                                  natural_timedelta, plural)


class Mod(LightningCog, required=["Configuration"]):
    """Moderation and server management commands."""

    @cache.cached('mod_config', cache.Strategy.lru)
    async def get_mod_config(self, guild_id):
        query = "SELECT * FROM guild_mod_config WHERE guild_id=$1;"
        record = await self.bot.pool.fetchrow(query, guild_id)
        return GuildModConfig(record) if record else None

    @cache.cached('logging', cache.Strategy.lru)
    async def get_logging_record(self, guild_id):
        records = await self.bot.pool.fetch("SELECT * FROM logging WHERE guild_id=$1;", guild_id)
        return LoggingConfig(records) if records else None

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    def format_reason(self, author, reason: str, *, action_text=None):
        reason = truncate_text(modlogformats.action_format(author, reason=reason), 512)
        return reason

    async def channelid_send(self, guild_id: int, channel_id: int, message=None, **kwargs):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            return await self.remove_mod_channel(guild_id)
        try:
            msg = await channel.send(message, **kwargs)
            return msg
        except discord.Forbidden:
            await self.remove_mod_channel(guild_id)

    async def add_punishment_role(self, guild_id: int, user_id: int, role_id: int) -> str:
        query = """INSERT INTO roles (guild_id, user_id, punishment_roles)
                   VALUES ($1, $2, $3::bigint[])
                   ON CONFLICT (guild_id, user_id)
                   DO UPDATE SET
                       punishment_roles =
                   ARRAY(SELECT DISTINCT * FROM unnest(COALESCE(roles.punishment_roles, '{}') || $3::bigint[]));"""
        return await self.bot.pool.execute(query, guild_id, user_id, [role_id])

    async def remove_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> None:
        query = """UPDATE roles SET punishment_roles = array_remove(punishment_roles, $1)
                   WHERE guild_id=$2 AND user_id=$3;"""
        connection = connection or self.bot.pool
        await connection.execute(query, role_id, guild_id, user_id)

    async def log_action(self, ctx: LightningContext, target, action: str, **kwargs) -> None:
        reason = ctx.kwargs.get('rest') or ctx.kwargs.get('reason')
        # We need this for bulk actions
        connection = kwargs.pop('connection', self.bot.pool)
        obj = Action(ctx.guild.id, action, target, ctx.author, reason, **kwargs)
        inf_id = await obj.add_infraction(connection)

        if obj.expiry:
            obj.expiry = natural_timedelta(obj.expiry, source=ctx.message.created_at)

        await self.do_log_message(obj.guild_id, obj.event, obj, inf_id)

    async def send_log_message(self, records, guild: discord.Guild, obj: Action, infraction_id: int) -> None:
        if not records:
            return

        for channel_id, record in records:
            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                fmt = modlogformats.MinimalisticFormat.from_action(obj, infraction_id)
                arg = False if record['format'] == "minimal without timestamp" else True
                msg = fmt.format_message(with_timestamp=arg)
                await channel.send(msg)
            elif record['format'] == "emoji":
                fmt = modlogformats.EmojiFormat.from_action(obj, infraction_id)
                msg = fmt.format_message()
                await channel.send(msg, allowed_mentions=discord.AllowedMentions(users=[obj.target, obj.moderator]))
            elif record['format'] == "embed":
                fmt = modlogformats.EmbedFormat.from_action(obj, infraction_id)
                embed = fmt.format_message()
                await channel.send(embed=embed)

    async def do_log_message(self, guild_id: int, action: Union[modlogformats.ActionType, str], obj: Action,
                             infraction_id: int) -> None:
        if not isinstance(action, modlogformats.ActionType):
            action = modlogformats.ActionType[str(action)]

        if str(action) == "TIMEMUTE":
            action = modlogformats.ActionType.MUTE

        if str(action) == "TIMEBAN":
            action = modlogformats.ActionType.BAN

        record = await self.get_logging_record(guild_id)
        if not record:
            return
        records = record.get_channels_with_feature(str(action).upper())
        await self.send_log_message(records, self.bot.get_guild(guild_id), obj, infraction_id)

    async def time_ban_user(self, ctx, target, moderator, reason, duration, *, dm_user=False,
                            delete_message_days=0) -> None:
        dt = get_utc_timestamp(duration.dt)
        timed_txt = natural_timedelta(duration.dt, source=ctx.message.created_at)
        duration_text = f"{timed_txt} ({dt})"
        cog = self.bot.get_cog('Reminders')
        if not cog:
            raise TimersUnavailable
        job_id = await cog.add_job("timeban", ctx.message.created_at, duration.dt, guild_id=ctx.guild.id,
                                   user_id=target.id, mod_id=moderator.id, force_insert=True)

        if dm_user and isinstance(target, discord.Member):
            dm_message = modlogformats.construct_dm_message(target, "banned", "from", reason=reason,
                                                            ending=f"\n\nThis ban expires in {duration_text}")
            await helpers.dm_user(target, dm_message)

        if reason:
            opt_reason = f"{reason} (Timeban expires in {duration_text})"
        else:
            opt_reason = f" (Timeban expires in {duration_text})"

        await ctx.guild.ban(target, reason=self.format_reason(ctx.author, opt_reason),
                            delete_message_days=delete_message_days)
        await ctx.send(f"{str(target)} is now banned. \N{THUMBS UP SIGN} It will expire in {duration_text}.")
        await self.log_action(ctx, target, "TIMEBAN",
                              expiry=duration.dt, timer_id=job_id)

    @dflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @commands.bot_has_guild_permissions(kick_members=True)
    @has_guild_permissions(kick_members=True)
    @command(cls=dflags.FlagCommand, level=CommandLevel.Mod)
    async def kick(self, ctx: LightningContext, target: converters.TargetMember(fetch_user=False), **flags) -> None:
        """Kicks a user from the server"""
        if not flags['nodm']:
            await helpers.dm_user(target, modlogformats.construct_dm_message(target, "kicked", "from",
                                  reason=flags['rest']))

        await ctx.guild.kick(target, reason=self.format_reason(ctx.author, flags['rest']))
        await ctx.send(f"{target} has been kicked. \N{OK HAND SIGN}")
        await self.log_action(ctx, target, "KICK")

    @dflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @dflags.add_flag("--duration", "--time", "-t", converter=FutureTime, help="Duration for the ban",
                     required=False)
    @dflags.add_flag("--delete-messages", converter=int, default=0,
                     help="Delete message history from a specified amount of days (Max 7)")
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    @command(cls=dflags.FlagCommand, level=CommandLevel.Mod)
    async def ban(self, ctx: LightningContext, target: converters.TargetMember, **flags) -> None:
        """Bans a user."""
        if flags['delete_messages'] < 0:
            raise commands.BadArgument("You can't delete a negative amount of messages.")
        reason = flags['rest']

        if flags['duration']:
            return await self.time_ban_user(ctx, target, ctx.author, reason, flags['duration'],
                                            dm_user=not flags['nodm'],
                                            delete_message_days=min(flags['delete_messages'], 7))

        if not flags['nodm'] and isinstance(target, discord.Member):
            dm_message = modlogformats.construct_dm_message(target, "banned", "from", reason=reason,
                                                            ending="\n\nThis ban does not expire.")
            await helpers.dm_user(target, dm_message)

        await ctx.guild.ban(target, reason=self.format_reason(ctx.author, reason),
                            delete_message_days=min(flags['delete_messages'], 7))
        await ctx.send(f"{target} is now banned. \N{THUMBS UP SIGN}")
        await self.log_action(ctx, target, "BAN")

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
                await helpers.dm_user(target, msg)
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
                       f"the server's warn ban limit of "\
                       f"{punishable_warn.warn_ban} warnings."
                msg += "\nIf you believe this to be in error, please message the staff."
        if isinstance(target, (discord.Member, discord.User)):
            if no_dm is False:
                await helpers.dm_user(target, msg)
            if punishable_warn.warn_kick:
                if warn_count == punishable_warn.warn_kick:
                    opt_reason = f"[AutoMod] Reached {warn_count} warns. "
                    try:
                        await ctx.guild.kick(target,
                                             reason=self.format_reason(ctx.author, opt_reason))
                    except discord.Forbidden:
                        return warn_count
                    self.bot.dispatch("automod_action", ctx.guild, "kick", target, opt_reason)
        if punishable_warn.warn_ban:
            if warn_count >= punishable_warn.warn_ban:  # just in case
                opt_reason = f"[AutoMod] Exceeded WarnBan Limit ({warn_count}). "
                try:
                    await ctx.guild.ban(target, reason=self.format_reason(ctx.author, opt_reason),
                                        delete_message_days=0)
                except discord.Forbidden:
                    return warn_count
                self.bot.dispatch("automod_action", ctx.guild, "ban", target, opt_reason)
        return warn_count

    @dflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @has_guild_permissions(manage_messages=True)
    @group(cls=dflags.FlagGroup, invoke_without_command=True, level=CommandLevel.Mod)
    async def warn(self, ctx: LightningContext, target: converters.TargetMember(fetch_user=False), **flags) -> None:
        """Warns a user"""
        no_dm = not flags['nodm']
        query = "SELECT COUNT(*) FROM infractions WHERE user_id=$1 AND guild_id=$2 AND action=$3;"
        warns = await self.bot.pool.fetchval(query, target.id, ctx.guild.id, modlogformats.ActionType.WARN.value) or 0
        warn_count = await self.warn_count_check(ctx, warns + 1, target,
                                                 flags['rest'], no_dm)
        await ctx.send(f"{target} warned. User now has {plural(warn_count):warning}.")
        await self.log_action(ctx, target, "WARN")

    @has_guild_permissions(manage_guild=True)
    @warn.group(name="punishments", aliases=['punishment'], invoke_without_command=True, level=CommandLevel.Admin)
    async def warn_punish(self, ctx: LightningContext) -> None:
        """Configures warn punishments for the server."""
        record = await self.get_mod_config(ctx.guild.id)
        if not record:
            await ctx.send("Warn punishments have not been setup.")
            return

        if record.warn_kick is None and record.warn_ban is None:
            await ctx.send("Warn punishments have not been setup.")
            return

        msg = ""
        if record.warn_kick:
            msg += f"Kick: at {record.warn_kick} warns\n"
        if record.warn_ban:
            msg += f"Ban: at {record.warn_ban}+ warns\n"
        await ctx.send(msg)

    @commands.bot_has_guild_permissions(kick_members=True)
    @has_guild_permissions(manage_guild=True)
    @warn_punish.command(name="kick", level=CommandLevel.Admin)
    async def warn_kick(self, ctx: LightningContext, number: converters.InbetweenNumber(1, 100)) -> None:
        """Configures the warn kick punishment.

        This kicks the member after acquiring a certain amount of warns."""
        query = """SELECT warn_ban
                   FROM guild_mod_config
                   WHERE guild_id=$1;"""
        ban_count = await self.bot.db.fetchval(query, ctx.guild.id)
        if ban_count:
            if number >= ban_count:
                await ctx.send("You cannot set the same or a higher value "
                               "for warn kick punishment "
                               "as the warn ban punishment.")
                return

        query = """INSERT INTO guild_mod_config (guild_id, warn_kick)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET warn_kick = EXCLUDED.warn_kick;
                """
        await self.bot.db.execute(query, ctx.guild.id, number)
        await self.get_mod_config.invalidate(ctx.guild.id)
        await ctx.send(f"Users will now get kicked if they reach "
                       f"{number} warns.")

    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(manage_guild=True)
    @warn_punish.command(name="ban", level=CommandLevel.Admin)
    async def warn_ban(self, ctx: LightningContext, number: converters.InbetweenNumber(1, 100)) -> None:
        """Configures the warn ban punishment.

        This bans the member after acquiring a certain amount of warns or higher."""
        query = """SELECT warn_kick
                   FROM guild_mod_config
                   WHERE guild_id=$1;"""
        kick_count = await self.bot.db.fetchval(query, ctx.guild.id)
        if kick_count:
            if number <= kick_count:
                await ctx.send("You cannot set the same or a lesser value for warn ban punishment "
                               "as the warn kick punishment.")
                return

        query = """INSERT INTO guild_mod_config (guild_id, warn_ban)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET warn_ban = EXCLUDED.warn_ban;
                """
        await self.bot.db.execute(query, ctx.guild.id, number)
        await self.get_mod_config.invalidate(ctx.guild.id)
        await ctx.send(f"Users will now get banned if they reach "
                       f"{number} or a higher amount of warns.")

    @has_guild_permissions(manage_guild=True)
    @warn_punish.command(name="clear", level=CommandLevel.Admin)
    async def warn_remove(self, ctx: LightningContext) -> None:
        """Removes all warn punishment configuration."""
        query = """UPDATE guild_mod_config
                   SET warn_ban=NULL,
                   warn_kick=NULL
                   WHERE guild_id=$1;
                """
        ret = await self.bot.db.execute(query, ctx.guild.id)
        await self.get_mod_config.invalidate(ctx.guild.id)
        if ret == "DELETE 0":
            await ctx.send("Warn punishments were never configured!")
            return

        await ctx.send("Removed warn punishment configuration!")

    async def do_message_purge(self, ctx: LightningContext, limit: int, predicate, *, before=None, after=None) -> None:
        if limit >= 150:
            resp = await ctx.prompt(f"Are you sure you want to purge {limit} messages?", delete_after=True)
            if not resp:
                await ctx.send("Cancelled")
                return

        if before is None:
            before = ctx.message
        else:
            before = discord.Object(id=before)
        if after is not None:
            after = discord.Object(id=after)

        try:
            purged = await ctx.channel.purge(limit=limit, before=before, after=after, check=predicate)
        except discord.Forbidden:
            raise commands.MissingPermissions([])
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
        await ctx.send(msg, delete_after=40)

    @commands.bot_has_permissions(manage_messages=True)
    @has_channel_permissions(manage_messages=True)
    @commands.group(invoke_without_command=True, aliases=['clear'], level=CommandLevel.Mod)
    async def purge(self, ctx: LightningContext, search: int) -> None:
        """Purges messages that meet a certain criteria.

        If called without a subcommand, the bot will remove all messages."""
        await self.do_message_purge(ctx, search, lambda m: True)

    @purge.error
    async def purge_error(self, ctx, error):
        if isinstance(error, LightningError):
            await ctx.send(error)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("You need to provide a number of messages to search!")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("Bot is missing Manage Messages permission")

    @commands.bot_has_permissions(manage_messages=True)
    @has_channel_permissions(manage_messages=True)
    @purge.command(name="user", level=CommandLevel.Mod)
    async def purge_from_user(self, ctx: LightningContext, member: discord.Member, search: int = 100) -> None:
        """Removes messages from a member"""
        await self.do_message_purge(ctx, search, lambda m: m.author == member)

    @commands.bot_has_permissions(manage_messages=True)
    @has_channel_permissions(manage_messages=True)
    @purge.command(name="attachments", aliases=['files'], level=CommandLevel.Mod)
    async def purge_files(self, ctx: LightningContext, search: int = 100) -> None:
        """Removes messages that contains attachments in the message."""
        await self.do_message_purge(ctx, search, lambda e: len(e.attachments))

    @commands.bot_has_permissions(manage_messages=True)
    @has_channel_permissions(manage_messages=True)
    @purge.command(name='contains', level=CommandLevel.Mod)
    async def purge_contains(self, ctx: LightningContext, *, string: str) -> None:
        """Removes messages containing a certain substring."""
        if len(string) < 5:
            raise commands.BadArgument("The string length must be at least 5 characters!")
        else:
            await self.do_message_purge(ctx, 100, lambda e: string in e.content)

    async def get_mute_role(self, ctx: LightningContext, *, temporary_role=False) -> discord.Role:
        """Gets the guild's mute role if it exists"""
        config = await self.get_mod_config(ctx.guild.id)
        if not config:
            raise MuteRoleError("You do not have a mute role set.")

        if temporary_role is False:
            return config.get_mute_role(ctx)
        else:
            return config.get_temp_mute_role(ctx)

    async def time_mute_user(self, ctx, target, reason, duration, *, dm_user=False):
        role = await self.get_mute_role(ctx, temporary_role=True)
        duration_text = get_utc_timestamp(duration.dt)
        timed_txt = natural_timedelta(duration.dt, source=ctx.message.created_at)
        duration_text = f"{timed_txt} ({duration_text})"
        timer = self.bot.get_cog('Reminders')
        if not timer:
            raise TimersUnavailable

        job_id = await timer.add_job("timemute", ctx.message.created_at,
                                     duration.dt, guild_id=ctx.guild.id, user_id=target.id, role_id=role.id,
                                     mod_id=ctx.author.id, force_insert=True)

        if dm_user:
            dm_message = f"You were muted in {ctx.guild.name}!"
            if reason:
                dm_message += f" The given reason is: \"{reason}\"."
            dm_message += f"\n\nThis mute will expire in {duration_text}."
            await helpers.dm_user(target, dm_message)

        if reason:
            opt_reason = f"{reason} (Timemute expires in {duration_text})"
        else:
            opt_reason = f" (Timemute expires in {duration_text})"

        if isinstance(target, discord.Member):
            await target.add_roles(role, reason=self.format_reason(ctx.author, opt_reason))

        await self.add_punishment_role(ctx.guild.id, target.id, role.id)
        await ctx.send(f"{str(target)} can no longer speak. It will expire in {duration_text}.")
        await self.log_action(ctx, target, "TIMEMUTE", expiry=duration.dt, timer_id=job_id)

    @dflags.add_flag("--duration", "-D", converter=FutureTime, help="Duration for the mute", required=False)
    @dflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @commands.bot_has_guild_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    @command(cls=dflags.FlagCommand, level=CommandLevel.Mod)
    async def mute(self, ctx: LightningContext, target: converters.TargetMember, **flags) -> None:
        """Mutes a user"""
        role = await self.get_mute_role(ctx)
        if flags['duration']:
            await self.time_mute_user(ctx, target, flags['rest'], flags['duration'], dm_user=not flags['nodm'])
            return

        if not flags['nodm']:
            dm_message = modlogformats.construct_dm_message(target, "muted", "in", reason=flags['rest'])
            await helpers.dm_user(target, dm_message)

        await target.add_roles(role, reason=self.format_reason(ctx.author, '[Mute]'))
        await self.add_punishment_role(ctx.guild.id, target.id, role.id)
        await ctx.send(f"{target} can no longer speak.")
        await self.log_action(ctx, target, "MUTE")

    async def punishment_role_check(self, guild_id, target_id, role_id, *, connection=None):
        query = """SELECT $3 = ANY(punishment_roles) FROM roles WHERE guild_id=$1 AND user_id=$2"""
        connection = connection or self.bot.pool
        return await connection.fetchval(query, guild_id, target_id, role_id)

    @command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    async def unmute(self, ctx: LightningContext, target: discord.Member, *,
                     reason: str = None) -> None:
        """Unmutes a user"""
        role = await self.get_mute_role(ctx)
        role_check_2 = await self.punishment_role_check(ctx.guild.id, target.id, role.id)
        if role not in target.roles or role_check_2 is None:
            await ctx.send('This user is not muted!')
            return

        # TODO: Update mute status
        await target.remove_roles(role, reason=f"{self.format_reason(ctx.author, '[Unmute]')}")
        await self.remove_punishment_role(ctx.guild.id, target.id, role.id)
        await ctx.send(f"{target} can now speak again.")
        await self.log_action(ctx, target, "UNMUTE")

    @command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    async def unban(self, ctx: LightningContext, member: converters.BannedMember, *, reason: str = "") -> None:
        """Unbans a user

        You can pass either the ID of the banned member or the Name#Discrim \
        combination of the member. The member's ID is easier to use."""
        await ctx.guild.unban(member.user, reason=self.format_reason(ctx.author, reason))
        await ctx.send(f"\N{OK HAND SIGN} {member.user} is now unbanned.")
        await self.log_action(ctx, member.user, "UNBAN")

    @command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    async def massban(self, ctx: LightningContext, members: commands.Greedy[converters.TargetMember],
                      *, reason: str) -> None:
        """Mass bans users from the server.

        Note: Users will not be notified about being banned from the server."""
        confirm = await ctx.prompt(f"Are you sure you want to ban {plural(len(members)):member}?")
        if not confirm:
            return

        async with self.bot.pool.acquire() as con:
            for member in members:
                await ctx.guild.ban(member, delete_message_days=0)
                await self.log_action(ctx, member, "BAN", connection=con)

    @dflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    @command(cls=dflags.FlagCommand, aliases=['tempban'])
    async def timeban(self, ctx: LightningContext, target: converters.TargetMember,
                      duration: FutureTime, **flags) -> None:
        """Bans a user for a specified amount of time.

        The duration can be a short time format such as "30d", \
        a more human duration format such as "until Monday at 7PM", \
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC."""
        await self.time_ban_user(ctx, target, ctx.author, flags['rest'], duration, dm_user=not flags['nodm'])

    @dflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @command(aliases=['tempmute'], level=CommandLevel.Mod, cls=dflags.FlagCommand)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    async def timemute(self, ctx: LightningContext, target: converters.TargetMember,
                       duration: FutureTime, **flags) -> None:
        """Mutes a user for a specified amount of time.

        The duration can be a short time format such as "30d", \
        a more human duration format such as "until Monday at 7PM", \
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC."""
        await self.time_mute_user(ctx, target, flags['rest'], duration, dm_user=not flags['nodm'])

    @commands.bot_has_permissions(manage_channels=True)
    @has_guild_permissions(manage_channels=True)
    @group(aliases=['lockdown'], invoke_without_command=True, level=CommandLevel.Mod)
    async def lock(self, ctx: LightningContext, channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Locks down the channel mentioned.

        Sets the channel permissions as @everyone can't send messages.

        If no channel was mentioned, it locks the channel the command was used in."""
        if channel.overwrites_for(ctx.guild.default_role).send_messages is False:
            await ctx.send(f"🔒 {channel.mention} is already locked down. "
                           f"Use `{ctx.prefix}unlock` to unlock.")
            return
        reason = modlogformats.action_format(ctx.author, "Lockdown done by")
        await channel.set_permissions(ctx.guild.default_role, reason=reason, send_messages=False,
                                      add_reactions=False)
        await channel.set_permissions(ctx.me, reason=reason, send_messages=True, manage_channels=True)
        await ctx.send(f"🔒 {channel.mention} is now locked.")

    @commands.bot_has_permissions(manage_channels=True)
    @has_guild_permissions(manage_channels=True)
    @lock.command(name="hard", level=CommandLevel.Admin)
    async def hlock(self, ctx: LightningContext,
                    channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Hard locks a channel.

        Sets the channel permissions as @everyone can't \
        send messages or read messages in the channel.

        If no channel was mentioned, it hard locks the channel the command was used in."""
        if channel.overwrites_for(ctx.guild.default_role).read_messages is False:
            await ctx.send(f"🔒 {channel.mention} is already hard locked. "
                           f"Use `{ctx.prefix}unlock hard` to unlock the channel.")
            return

        reason = modlogformats.action_format(ctx.author, "Hard lockdown done by")
        await channel.set_permissions(ctx.guild.default_role, reason=reason, read_messages=False,
                                      send_messages=False)
        await channel.set_permissions(ctx.me, reason=reason, read_messages=True,
                                      send_messages=True, manage_channels=True)
        await ctx.send(f"🔒 {channel.mention} is now hard locked.")

    @commands.bot_has_permissions(manage_channels=True)
    @has_guild_permissions(manage_channels=True)
    @group(invoke_without_command=True)
    async def unlock(self, ctx: LightningContext,
                     channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Unlocks the channel mentioned.

        If no channel was mentioned, it unlocks the channel the command was used in."""
        if channel.overwrites_for(ctx.guild.default_role).send_messages is None:
            await ctx.send(f"🔓 {channel.mention} is already unlocked.")
            return
        reason = modlogformats.action_format(ctx.author, "Lockdown removed by")
        await channel.set_permissions(ctx.guild.default_role, reason=reason, send_messages=None,
                                      add_reactions=None)
        await ctx.send(f"🔓 {channel.mention} is now unlocked.")

    @commands.bot_has_permissions(manage_channels=True)
    @has_guild_permissions(manage_channels=True)
    @unlock.command(name='hard')
    async def hunlock(self, ctx: LightningContext,
                      channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Hard unlocks the channel mentioned.

        If no channel was mentioned, it unlocks the channel the command was used in."""
        if channel.overwrites_for(ctx.guild.default_role).read_messages is None:
            await ctx.send(f"🔓 {channel.mention} is already unlocked.")
            return
        reason = modlogformats.action_format(ctx.author, "Hard lockdown removed by")
        await channel.set_permissions(ctx.guild.default_role, reason=reason,
                                      read_messages=None, send_messages=None)
        await ctx.send(f"🔓 {channel.mention} is now unlocked.")

    @commands.bot_has_permissions(manage_messages=True)
    @has_channel_permissions(manage_messages=True)
    @command(level=CommandLevel.Mod)
    async def pin(self, ctx: LightningContext, message_id: int,
                  channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Pins a message by ID."""
        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("Message ID not found.")
            return

        try:
            await msg.pin(reason=modlogformats.action_format(ctx.author))
        except discord.HTTPException as e:
            await self.bot.log_command_error(ctx, e)
            return

        await ctx.send("\N{OK HAND SIGN}")

    @commands.bot_has_permissions(manage_messages=True)
    @has_channel_permissions(manage_messages=True)
    @command(level=CommandLevel.Mod)
    async def unpin(self, ctx: LightningContext, message_id: int,
                    channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Unpins a message by ID."""
        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("Message ID not found.")
            return

        try:
            await msg.unpin(reason=modlogformats.action_format(ctx.author))
        except discord.HTTPException as e:
            await self.bot.log_command_error(ctx, e)
            return

        await ctx.send("\N{OK HAND SIGN}")

    @has_guild_permissions(manage_messages=True)
    @command(level=CommandLevel.Mod)
    async def clean(self, ctx: LightningContext, search: int = 100,
                    channel: discord.TextChannel = commands.default.CurrentChannel) -> None:
        """Cleans the bot's messages from the channel specified.

        If no channel is specified, the bot deletes its \
        messages from the channel the command was run in.

        If a search number is specified, it will search \
        that many messages from the bot in the specified channel and clean them."""
        if (search > 100):
            raise commands.BadArgument("Cannot purge more than 100 messages.")
        has_perms = ctx.channel.permissions_for(ctx.guild.me).manage_messages
        await channel.purge(limit=search, check=lambda b: b.author == ctx.bot.user,
                            before=ctx.message.created_at,
                            after=datetime.utcnow() - timedelta(days=14),
                            bulk=has_perms)
        await ctx.send("\N{OK HAND SIGN}", delete_after=15)

    # Automod
    @command(hidden=True)
    async def raidmode(self, ctx: LightningContext) -> None:
        ...

    async def log_timed_action_complete(self, timer, action, feature, guild, user, moderator) -> None:
        record = await self.get_logging_record(guild.id)
        if not record:
            return

        records = record.get_channels_with_feature(feature)
        if not records:
            return

        for channel_id, record in records:
            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                arg = False if record['format'] == "minimal without timestamp" else True
                message = modlogformats.MinimalisticFormat.timed_action_expired(action.lower(), user, moderator,
                                                                                timer.created_at, timer.expiry,
                                                                                with_timestamp=arg)
                await channel.send(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.timed_action_expired(action.lower(), user, moderator,
                                                                         timer.created_at)
                await channel.send(message, allowed_mentions=discord.AllowedMentions(users=[user, moderator]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.timed_action_expired(action.lower(), moderator, user,
                                                                       timer.created_at)
                await channel.send(embed=embed)

    @LightningCog.listener()
    async def on_timeban_job_complete(self, timer):
        # Update timeban status
        query = "UPDATE infractions SET active=false WHERE guild_id=$1 AND user_id=$2 AND expiry=$3 AND action='4';"
        await self.bot.pool.execute(query, timer.extra['guild_id'], timer.extra['user_id'], timer.expiry)

        guild = self.bot.get_guild(timer.extra['guild_id'])
        if guild is None:
            # Bot was kicked.
            return

        try:
            uid = await self.bot.fetch_user(timer.extra['user_id'])
        except Exception:
            uid = helpers.BetterUserObject(id=timer.extra['user_id'])

        moderator = guild.get_member(timer.extra['mod_id'])
        if moderator is None:
            try:
                moderator = await self.bot.fetch_user(timer.extra['mod_id'])
            except Exception:
                # Discord Broke/Failed/etc.
                mod = f"Moderator ID {timer.extra['mod_id']}"
            else:
                mod = f'{moderator} (ID: {moderator.id})'
        else:
            mod = f'{moderator} (ID: {moderator.id})'

        reason = f"Timed ban made by {mod} at {timer.created_at} expired"
        await guild.unban(uid, reason=reason)
        await self.log_timed_action_complete(timer, "ban", "UNBAN", guild, uid, moderator)

    @LightningCog.listener()
    async def on_timemute_job_complete(self, timer):
        async with self.bot.pool.acquire() as connection:
            if await self.punishment_role_check(timer.extra['guild_id'],
                                                timer.extra['user_id'],
                                                timer.extra['role_id'], connection=connection) is None:
                return

            await self.remove_punishment_role(timer.extra['guild_id'], timer.extra['user_id'],
                                              timer.extra['role_id'], connection=connection)
            query = "UPDATE infractions SET active=false WHERE guild_id=$1 AND user_id=$2 AND expiry=$3;"
            await connection.execute(query, timer.extra['guild_id'], timer.extra['user_id'], timer.expiry)

        guild = self.bot.get_guild(timer.extra['guild_id'])
        if guild is None:
            # Bot was kicked.
            return

        moderator = guild.get_member(timer.extra['mod_id'])
        if moderator is None:
            try:
                mod = await self.bot.fetch_user(timer.extra['mod_id'])
            except Exception:
                # Discord Broke/Failed/etc.
                mod = f"Moderator ID {timer.extra['mod_id']}"
            else:
                mod = f'{moderator} (ID: {moderator.id})'
        else:
            mod = f'{moderator} (ID: {moderator.id})'

        role = guild.get_role(timer.extra['role_id'])
        if role is None:
            # Role was deleted or something.
            return

        user = guild.get_member(timer.extra['user_id'])
        if user is None:
            # User left probably...
            user = helpers.BetterUserObject(timer.extra['user_id'])
        else:
            reason = f"Timed mute made by {mod} at {get_utc_timestamp(timer.created)} expired"
            # I think I'll intentionally let it raise an error if bot missing perms or w/e...
            await user.remove_roles(role, reason=reason)

        await self.log_timed_action_complete(timer, "mute", "UNMUTE", guild, user, moderator)

    # Logging
    # -------
    async def fetch_audit_log_entry(self, guild, action, *, target=None, limit: int = 50):
        async for entry in guild.audit_logs(limit=limit, action=action):
            td = datetime.utcnow() - entry.created_at
            if td < timedelta(seconds=10):
                if target is not None and entry.target == target:
                    return entry
                else:
                    continue
            else:
                continue

        return None

    @LightningCog.listener()
    async def on_member_ban(self, guild, user):
        await self.bot.wait_until_ready()
        # Wait for Audit Log to update
        await asyncio.sleep(0.5)

        if not guild.me.guild_permissions.view_audit_log:
            return

        entry = await self.fetch_audit_log_entry(guild, discord.AuditLogAction.ban, target=user)
        if entry.user == self.bot.user:
            # Assuming it's already logged
            return

        obj = Action(guild.id, "BAN", user, entry.user, entry.reason or None)
        inf_id = await obj.add_infraction(self.bot.pool)
        await self.do_log_message(obj.guild_id, obj.event, obj, inf_id)

    @LightningCog.listener()
    async def on_member_unban(self, guild, user):
        await self.bot.wait_until_ready()
        # Wait for Audit Log to update
        await asyncio.sleep(0.5)

        if not guild.me.guild_permissions.view_audit_log:
            return

        entry = await self.fetch_audit_log_entry(guild, discord.AuditLogAction.unban, target=user)
        if entry.user == self.bot.user:
            # Assuming it's already logged
            return

        obj = Action(guild.id, "UNBAN", user, entry.user, entry.reason or None)
        inf_id = await obj.add_infraction(self.bot.pool)
        await self.do_log_message(obj.guild_id, obj.event, obj, inf_id)

    async def get_records(self, guild, feature):
        record = await self.get_logging_record(guild.id)
        if not record:
            return

        records = record.get_channels_with_feature(feature)
        if not records:
            return

        for channel_id, record in records:
            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            yield channel, record

    @LightningCog.listener()
    async def on_member_join(self, member):
        await self.bot.wait_until_ready()

        guild = member.guild
        async for channel, record in self.get_records(guild, "MEMBER_JOIN"):
            if record['format'] == "minimal with timestamp":
                message = modlogformats.MinimalisticFormat.join_leave("MEMBER_JOIN", member)
                await channel.send(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.join_leave("MEMBER_JOIN", member)
                await channel.send(message, allowed_mentions=discord.AllowedMentions(users=[member]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.join_leave("MEMBER_JOIN", member)
                await channel.send(embed=embed)

    @LightningCog.listener()
    async def on_member_remove(self, member):
        await self.bot.wait_until_ready()

        guild = member.guild
        async for channel, record in self.get_records(guild, "MEMBER_LEAVE"):
            if record['format'] == "minimal with timestamp":
                message = modlogformats.MinimalisticFormat.join_leave("MEMBER_LEAVE", member)
                await channel.send(message)
            elif record['format'] == "emoji":
                message = modlogformats.EmojiFormat.join_leave("MEMBER_LEAVE", member)
                await channel.send(message, allowed_mentions=discord.AllowedMentions(users=[member]))
            elif record['format'] == "embed":
                embed = modlogformats.EmbedFormat.join_leave("MEMBER_LEAVE", member)
                await channel.send(embed=embed)

        # Kick stuff
        if not guild.me.guild_permissions.view_audit_log:
            return

        entry = await self.fetch_audit_log_entry(guild, discord.AuditLogAction.kick, target=member)
        if member.joined_at is None or member.joined_at > entry.created_at:
            return

        if entry.user == self.bot.user:
            # Assuming it's already logged
            return

        obj = Action(guild.id, "KICK", member, entry.user, entry.reason or None)
        inf_id = await obj.add_infraction(self.bot.pool)
        await self.do_log_message(obj.guild_id, obj.event, obj, inf_id)

    async def find_occurance(self, guild, action, match, limit=50, retry=True):
        if not guild.me.guild_permissions.view_audit_log:
            return

        entry = None
        async for e in guild.audit_logs(action=action, limit=limit):
            if match(e):
                if entry is None or e.id > entry.id:
                    entry = e
                    break

        if entry is None and retry:
            await asyncio.sleep(2)
            return await self.find_occurance(guild, action, match, limit, False)
        # if entry is not None and isinstance(entry.target, discord.Object):
        #    entry.target = await self.bot.get_user(entry.target.id)
        return entry

    @LightningCog.listener()
    async def on_member_update(self, before, after):
        await self.bot.wait_until_ready()
        guild = before.guild

        if before.roles != after.roles:
            added = [role for role in after.roles if role not in before.roles]
            removed = [role for role in before.roles if role not in after.roles]
            if (len(added) + len(removed)) == 0:
                return

            def check(e):
                return e.target.id == before.id and hasattr(e.changes.before, "roles") \
                    and hasattr(e.changes.after, "roles") and \
                    all(r in e.changes.before.roles for r in removed) and \
                    all(r in e.changes.after.roles for r in added)

            entry = await self.find_occurance(guild, discord.AuditLogAction.member_role_update,
                                              check)

            async for channel, record in self.get_records(guild, "MEMBER_ROLE_CHANGE"):
                if record['format'] in ("minimal with timestamp", "minimal without timestamp"):
                    arg = False if record['format'] == "minimal without timestamp" else True
                    message = modlogformats.MinimalisticFormat.role_change(after, added, removed, entry=entry,
                                                                           with_timestamp=arg)
                    await channel.send(message)
                elif record['format'] == "emoji":
                    message = modlogformats.EmojiFormat.role_change(added, removed, after, entry=entry)
                    await channel.send(message)
                elif record['format'] == "embed":
                    embed = modlogformats.EmbedFormat.role_change(after, added, removed, entry=entry)
                    await channel.send(embed=embed)


def setup(bot) -> None:
    bot.add_cog(Mod(bot))
