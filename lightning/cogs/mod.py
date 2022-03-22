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

from collections import Counter
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, Union

import discord
from discord.ext import commands

from lightning import (CommandLevel, LightningCog, LightningContext, ModFlags,
                       cache, command, converters)
from lightning import flags as lflags
from lightning import group
from lightning.errors import LightningError, MuteRoleError, TimersUnavailable
from lightning.events import InfractionEvent
from lightning.formatters import plural, truncate_text
from lightning.models import GuildModConfig, PartialGuild
from lightning.utils import helpers, modlogformats
from lightning.utils.checks import (has_channel_permissions,
                                    has_guild_permissions)
from lightning.utils.time import (FutureTime, get_utc_timestamp,
                                  natural_timedelta)

if TYPE_CHECKING:
    from lightning.cogs.reminders import Reminders

confirmations = {"ban": "{target} was banned. \N{THUMBS UP SIGN}",
                 "timeban": "{target} was banned. \N{THUMBS UP SIGN} It will expire in {expiry}.",
                 "kick": "{target} was kicked. \N{OK HAND SIGN}",
                 "warn": "{target} was warned. ({count})",
                 "mute": "{target} can no longer speak.",
                 "timemute": "{target} can no longer speak. It will expire in {expiry}.",
                 "unmute": "{target} can now speak again.",
                 "unban": "\N{OK HAND SIGN} {target} is now unbanned."}


BaseModParser = lflags.FlagParser([lflags.Flag("--nodm", "--no-dm", is_bool_flag=True,
                                   help="Bot does not DM the user the reason for the action.")],
                                  rest_attribute_name="reason", raise_on_bad_flag=False)


COMMON_HOIST_CHARACTERS = ["!", "-", "/", "*", "(", ")", "+", "[", "]", "#", "<", ">", "_", ".", "$", "\"", "?"]


class Mod(LightningCog, required=["Configuration"]):
    """Moderation and server management commands."""

    @cache.cached('mod_config', cache.Strategy.lru)
    async def get_mod_config(self, guild_id: int) -> Optional[GuildModConfig]:
        query = "SELECT * FROM guild_mod_config WHERE guild_id=$1;"
        record = await self.bot.pool.fetchrow(query, guild_id)
        return GuildModConfig(record, self.bot) if record else None

    async def cog_check(self, ctx: LightningContext) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    def format_reason(self, author, reason: str, *, action_text=None) -> str:
        return truncate_text(modlogformats.action_format(author, action_text, reason=reason), 512)

    async def add_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> str:
        query = """INSERT INTO roles (guild_id, user_id, punishment_roles)
                   VALUES ($1, $2, $3::bigint[])
                   ON CONFLICT (guild_id, user_id)
                   DO UPDATE SET
                       punishment_roles =
                   ARRAY(SELECT DISTINCT * FROM unnest(COALESCE(roles.punishment_roles, '{}') || $3::bigint[]));"""
        connection = connection or self.bot.pool
        return await connection.execute(query, guild_id, user_id, [role_id])

    async def remove_punishment_role(self, guild_id: int, user_id: int, role_id: int, *, connection=None) -> None:
        query = """UPDATE roles SET punishment_roles = array_remove(punishment_roles, $1)
                   WHERE guild_id=$2 AND user_id=$3;"""
        connection = connection or self.bot.pool
        await connection.execute(query, role_id, guild_id, user_id)

    async def log_manual_action(self, guild: discord.Guild, target, moderator,
                                action: Union[modlogformats.ActionType, str], *, timestamp=None,
                                reason: Optional[str] = None, **kwargs) -> None:
        # We need this for bulk actions
        connection = kwargs.pop('connection', self.bot.pool)

        timestamp = timestamp or discord.utils.utcnow()

        event = InfractionEvent(action, member=target, guild=guild, moderator=moderator, reason=reason, **kwargs)
        await event.action.add_infraction(connection)

        if not isinstance(action, modlogformats.ActionType):
            action = modlogformats.ActionType[str(action)]

        if str(action) == "TIMEMUTE":
            action = modlogformats.ActionType.MUTE

        if str(action) == "TIMEBAN":
            action = modlogformats.ActionType.BAN

        if event.action.expiry:
            event.action.expiry = natural_timedelta(event.action.expiry, source=timestamp)

        self.bot.dispatch(f"lightning_member_{str(action).lower()}", event)

    async def log_action(self, ctx: LightningContext, target, action: str, **kwargs) -> None:
        reason = ctx.kwargs.get('rest') or ctx.kwargs.get('reason')

        await self.log_manual_action(ctx.guild, target, ctx.author, action, timestamp=ctx.message.created_at,
                                     reason=reason, **kwargs)

    async def log_bulk_actions(self, ctx: LightningContext, targets: list, action: str, **kwargs) -> None:
        """Logs a bunch of actions"""
        async with self.bot.pool.acquire() as conn:
            for target in targets:
                await self.log_action(ctx, target, action, connection=conn, **kwargs)

    async def confirm_and_log_action(self, ctx: LightningContext, target, action: str, **kwargs) -> None:
        duration_text = kwargs.pop("duration_text", None)
        warning_text = kwargs.pop("warning_text", None)

        record = await self.get_mod_config(ctx.guild.id)
        if not record:
            await ctx.send(confirmations.get(action.lower(), "Done!").format(target=target,
                                                                             expiry=duration_text,
                                                                             count=warning_text))
            await self.log_action(ctx, target, action, **kwargs)
            return

        if record.flags and ModFlags.react_only_confirmation in record.flags:
            try:
                await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
            except (discord.Forbidden, discord.HTTPException):
                pass

            await self.log_action(ctx, target, action, **kwargs)
            return

        if record.flags and ModFlags.hide_confirmation_message in record.flags:
            await self.log_action(ctx, target, action, **kwargs)
            return

        await ctx.send(confirmations.get(action.lower(), "Done!").format(target=target, expiry=duration_text,
                                                                         count=warning_text))

        await self.log_action(ctx, target, action, **kwargs)

    @command(cls=lflags.FlagCommand, level=CommandLevel.Mod, parser=BaseModParser)
    @commands.bot_has_guild_permissions(kick_members=True)
    @has_guild_permissions(kick_members=True)
    async def kick(self, ctx: LightningContext, target: converters.TargetMember(fetch_user=False), **flags) -> None:
        """Kicks a user from the server"""
        if not flags['nodm']:  # No check is done here since we don't fetch users
            await helpers.dm_user(target, modlogformats.construct_dm_message(target, "kicked", "from",
                                  reason=flags['reason']))

        await ctx.guild.kick(target, reason=self.format_reason(ctx.author, flags['reason']))
        await self.confirm_and_log_action(ctx, target, "KICK")

    async def time_ban_user(self, ctx, target, moderator, reason, duration, *, dm_user=False,
                            delete_message_days=0) -> None:
        duration_text = f"{natural_timedelta(duration.dt, source=ctx.message.created_at)} ("\
                        f"{discord.utils.format_dt(duration.dt)})"

        cog: Optional[Reminders] = self.bot.get_cog('Reminders')
        if not cog:
            raise TimersUnavailable

        job_id = await cog.add_timer("timeban", ctx.message.created_at, duration.dt, guild_id=ctx.guild.id,
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
        await self.confirm_and_log_action(ctx, target, "TIMEBAN", duration_text=duration_text,
                                          expiry=duration.dt, timer_id=job_id)

    @lflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @lflags.add_flag("--duration", "--time", "-t", converter=FutureTime, help="Duration for the ban",
                     required=False)
    @lflags.add_flag("--delete-messages", converter=int, default=0,
                     help="Delete message history from a specified amount of days (Max 7)")
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    @command(cls=lflags.FlagCommand, level=CommandLevel.Mod, rest_attribute_name="reason",
             raise_bad_flag=False)
    async def ban(self, ctx: LightningContext, target: converters.TargetMember, **flags) -> None:
        """Bans a user from the server."""
        if flags['delete_messages'] < 0:
            raise commands.BadArgument("You can't delete a negative amount of messages.")

        reason = flags['reason']

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
        await self.confirm_and_log_action(ctx, target, "BAN")

    @has_guild_permissions(manage_messages=True)
    @group(cls=lflags.FlagGroup, invoke_without_command=True, level=CommandLevel.Mod, parser=BaseModParser)
    async def warn(self, ctx: LightningContext, target: converters.TargetMember(fetch_user=False), **flags) -> None:
        """Warns a user"""
        if not flags['nodm'] and isinstance(target, discord.Member):
            dm_message = modlogformats.construct_dm_message(target, "warned", "in", reason=flags['reason'])
            # ending="\n\nAdditional action may be taken against you if the server has set it up."
            await helpers.dm_user(target, dm_message)

        query = "SELECT COUNT(*) FROM infractions WHERE user_id=$1 AND guild_id=$2 AND action=$3;"
        warns = await self.bot.pool.fetchval(query, target.id, ctx.guild.id, modlogformats.ActionType.WARN.value) or 0
        await self.confirm_and_log_action(ctx, target, "WARN", warning_text=f"{plural(warns + 1):warning}")

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
        ban_count = await self.bot.pool.fetchval(query, ctx.guild.id)
        if ban_count and number >= ban_count:
            await ctx.send("You cannot set the same or a higher value "
                           "for warn kick punishment "
                           "as the warn ban punishment.")
            return

        query = """INSERT INTO guild_mod_config (guild_id, warn_kick)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET warn_kick = EXCLUDED.warn_kick;
                """
        await self.bot.pool.execute(query, ctx.guild.id, number)
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
        kick_count = await self.bot.pool.fetchval(query, ctx.guild.id)
        if kick_count and number <= kick_count:
            await ctx.send("You cannot set the same or a lesser value for warn ban punishment "
                           "as the warn kick punishment.")
            return

        query = """INSERT INTO guild_mod_config (guild_id, warn_ban)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id)
                   DO UPDATE SET warn_ban = EXCLUDED.warn_ban;
                """
        await self.bot.pool.execute(query, ctx.guild.id, number)
        await self.get_mod_config.invalidate(ctx.guild.id)
        await ctx.send("Users will now get banned if they reach "
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
        ret = await self.bot.pool.execute(query, ctx.guild.id)
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

        before = ctx.message if before is None else discord.Object(id=before)
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
            return config.get_mute_role()
        else:
            return config.get_temp_mute_role()

    async def time_mute_user(self, ctx, target, reason, duration, *, dm_user=False):
        role = await self.get_mute_role(ctx, temporary_role=True)
        duration_text = f"{natural_timedelta(duration.dt, source=ctx.message.created_at)} ("\
                        f"{discord.utils.format_dt(duration.dt)})"

        timer: Optional[Reminders] = self.bot.get_cog('Reminders')
        if not timer:
            raise TimersUnavailable

        job_id = await timer.add_timer("timemute", ctx.message.created_at,
                                       duration.dt, guild_id=ctx.guild.id, user_id=target.id, role_id=role.id,
                                       mod_id=ctx.author.id, force_insert=True)

        if isinstance(target, discord.Member):
            msg = modlogformats.construct_dm_message(target, "muted", "in", reason=reason,
                                                     ending=f"\n\nThis mute will expire in {duration_text}.")
            await helpers.dm_user(target, msg)

            if reason:
                opt_reason = f"{reason} (Timemute expires in {duration_text})"
            else:
                opt_reason = f" (Timemute expires in {duration_text})"
            await target.add_roles(role, reason=self.format_reason(ctx.author, opt_reason))

        await self.add_punishment_role(ctx.guild.id, target.id, role.id)
        await self.confirm_and_log_action(ctx, target, "TIMEMUTE", duration_text=duration_text, expiry=duration.dt,
                                          timer_id=job_id)

    @lflags.add_flag("--duration", "-D", converter=FutureTime, help="Duration for the mute", required=False)
    @lflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @commands.bot_has_guild_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    @command(cls=lflags.FlagCommand, level=CommandLevel.Mod, rest_attribute_name="reason", raise_bad_flag=False)
    async def mute(self, ctx: LightningContext, target: converters.TargetMember, **flags) -> None:
        """Mutes a user"""
        role = await self.get_mute_role(ctx)
        if flags['duration']:
            await self.time_mute_user(ctx, target, flags['reason'], flags['duration'], dm_user=not flags['nodm'])
            return

        if not flags['nodm'] and isinstance(target, discord.Member):
            dm_message = modlogformats.construct_dm_message(target, "muted", "in", reason=flags['reason'])
            await helpers.dm_user(target, dm_message)

        await target.add_roles(role, reason=self.format_reason(ctx.author, '[Mute]'))
        await self.add_punishment_role(ctx.guild.id, target.id, role.id)
        await self.confirm_and_log_action(ctx, target, "MUTE")

    async def punishment_role_check(self, guild_id, target_id, role_id, *, connection=None):
        """Checks if a role is currently attached to a user.

        Returns
        -------
        bool
            True if the role is currently attached. False is the role is not attached."""
        query = """SELECT $3 = ANY(punishment_roles) FROM roles WHERE guild_id=$1 AND user_id=$2"""
        connection = connection or self.bot.pool
        val = await connection.fetchval(query, guild_id, target_id, role_id)
        return bool(val)

    async def update_last_mute(self, guild_id, user_id, *, connection=None):
        connection = connection or self.bot.pool
        query = """SELECT id FROM infractions
                   WHERE guild_id=$1
                   AND user_id=$2
                   AND action='6'
                   ORDER BY created_at DESC
                   LIMIT 1;
                """
        val = await connection.fetchval(query, guild_id, user_id)

        query = """UPDATE infractions
                   SET active=false
                   WHERE guild_id=$1 AND id=$2;
                """
        return await connection.execute(query, guild_id, val)

    @command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    async def unmute(self, ctx: LightningContext, target: discord.Member, *,
                     reason: str = None) -> None:
        """Unmutes a user"""
        role = await self.get_mute_role(ctx)
        check = await self.punishment_role_check(ctx.guild.id, target.id, role.id)
        if role not in target.roles or check is False:
            await ctx.send('This user is not muted!')
            return

        await self.update_last_mute(ctx.guild.id, target.id)
        await self.remove_punishment_role(ctx.guild.id, target.id, role.id)

        try:
            await target.remove_roles(role, reason=self.format_reason(ctx.author, '[Unmute]'))
        except discord.Forbidden:
            await ctx.send(f"Unable to remove the mute role from {str(target)}'s roles.")
        else:
            await ctx.send(f"{target} can now speak again.")

        await self.log_action(ctx, target, "UNMUTE")

    @command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    async def unban(self, ctx: LightningContext, member: converters.BannedMember, *, reason: str = None) -> None:
        """Unbans a user

        You can pass either the ID of the banned member or the Name#Discrim \
        combination of the member. The member's ID is easier to use."""
        await ctx.guild.unban(member.user, reason=self.format_reason(ctx.author, reason))
        await self.confirm_and_log_action(ctx, member.user, "UNBAN")

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

    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    @command(cls=lflags.FlagCommand, aliases=['tempban'], level=CommandLevel.Mod, parser=BaseModParser)
    async def timeban(self, ctx: LightningContext, target: converters.TargetMember,
                      duration: FutureTime, **flags) -> None:
        """Bans a user for a specified amount of time.

        The duration can be a short time format such as "30d", \
        a more human duration format such as "until Monday at 7PM", \
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC."""
        await self.time_ban_user(ctx, target, ctx.author, flags['reason'], duration, dm_user=not flags['nodm'])

    @command(aliases=['tempmute'], level=CommandLevel.Mod, cls=lflags.FlagCommand, parser=BaseModParser)
    @commands.bot_has_guild_permissions(manage_roles=True)
    @has_guild_permissions(manage_roles=True)
    async def timemute(self, ctx: LightningContext, target: converters.TargetMember,
                       duration: FutureTime, **flags) -> None:
        """Mutes a user for a specified amount of time.

        The duration can be a short time format such as "30d", \
        a more human duration format such as "until Monday at 7PM", \
        or a more concrete time format such as "2020-12-31".

        Note that duration time is in UTC."""
        await self.time_mute_user(ctx, target, flags['reason'], duration, dm_user=not flags['nodm'])

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
        await ctx.send(f"\N{LOCK} {channel.mention} is now locked.")

    @lock.command(name="thread", level=CommandLevel.Mod)
    @has_channel_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def lock_thread(self, ctx: LightningContext, thread: discord.Thread = commands.default.CurrentChannel):
        if not isinstance(thread, discord.Thread):
            raise commands.BadArgument("This doesn't seem to be a thread.")

        if thread.locked and thread.archived is True:
            await ctx.send("This thread is already locked.")
            return

        await thread.edit(archived=True, locked=True)

        # If we send a message or do anything else, we undo the lock state of the thread.
        if ctx.channel != thread:
            await ctx.send(f"\N{LOCK} {thread.mention} is now locked!")

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
    @group(invoke_without_command=True, level=CommandLevel.Mod)
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
    @unlock.command(name='hard', level=CommandLevel.Admin)
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

    async def dehoist_member(self, member: discord.Member, moderator, characters: list):
        old_nick = member.display_name
        new_nick = old_nick

        for char in old_nick:
            if char not in characters:
                break

            new_nick = new_nick[1:]

        if len(new_nick) == 0:
            new_nick = "don't hoist"

        if old_nick == new_nick:
            return False

        await member.edit(nick=new_nick, reason=self.format_reason(moderator, None, action_text="Dehoist done by"))

        if old_nick != new_nick:
            return True

    @has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @commands.cooldown(1, 300.0, commands.BucketType.guild)
    @command(level=CommandLevel.Mod)
    async def dehoist(self, ctx: LightningContext, character: Optional[str]):
        """Dehoists members with an optional specified character in the beginning of their name"""
        character = [character] if character else COMMON_HOIST_CHARACTERS
        dehoists = []
        failed_dehoist = []

        async with ctx.typing():
            for member in ctx.guild.members:
                try:
                    i = await self.dehoist_member(member, ctx.author, character)
                except discord.HTTPException:
                    failed_dehoist.append(member)
                    continue

                if i:
                    dehoists.append(member)

        await ctx.send(f"Dehoisted {len(dehoists)}/{len(ctx.guild.members)}\n{len(failed_dehoist)} failed.")

    @LightningCog.listener()
    async def on_lightning_timeban_complete(self, timer):
        # We need to update timeban status first. Eventually, we need to move this over to infractions cog but idk
        query = "UPDATE infractions SET active=false WHERE guild_id=$1 AND user_id=$2 AND expiry=$3 AND action='4';"
        await self.bot.pool.execute(query, timer.extra['guild_id'], timer.extra['user_id'], timer.expiry)

        guild = self.bot.get_guild(timer.extra['guild_id'])
        if guild is None:
            # Bot was kicked.
            return

        try:
            user = await self.bot.fetch_user(timer.extra['user_id'])
        except Exception:
            user = helpers.BetterUserObject(id=timer.extra['user_id'])

        moderator = guild.get_member(timer.extra['mod_id']) or helpers.BetterUserObject(id=timer.extra['mod_id'])

        reason = f"Timed ban made by {modlogformats.base_user_format(moderator)} at {timer.created_at} expired"
        await guild.unban(user, reason=reason)
        self.bot.dispatch("lightning_timed_moderation_action_done", "UNBAN", guild, user, moderator, timer)

    @LightningCog.listener()
    async def on_lightning_timemute_complete(self, timer):
        async with self.bot.pool.acquire() as connection:
            if await self.punishment_role_check(timer.extra['guild_id'],
                                                timer.extra['user_id'],
                                                timer.extra['role_id'], connection=connection) is False:
                return

            await self.remove_punishment_role(timer.extra['guild_id'], timer.extra['user_id'],
                                              timer.extra['role_id'], connection=connection)
            query = "UPDATE infractions SET active=false WHERE guild_id=$1 AND user_id=$2 AND expiry=$3 AND action='8';"
            await connection.execute(query, timer.extra['guild_id'], timer.extra['user_id'], timer.expiry)

        guild = self.bot.get_guild(timer.extra['guild_id'])
        if guild is None:
            # Bot was kicked.
            return

        moderator = guild.get_member(timer.extra['mod_id']) or helpers.BetterUserObject(timer.extra['mod_id'])

        role = guild.get_role(timer.extra['role_id'])
        if role is None:
            # Role was deleted or something.
            return

        user = guild.get_member(timer.extra['user_id'])
        if user is None:
            # User left probably...
            user = helpers.BetterUserObject(timer.extra['user_id'])
        else:
            reason = f"Timed mute made by {modlogformats.base_user_format(moderator)} at "\
                     f"{get_utc_timestamp(timer.created)} expired"
            # I think I'll intentionally let it raise an error if bot missing perms or w/e...
            await user.remove_roles(role, reason=reason)

        self.bot.dispatch("lightning_timed_moderation_action_done", "UNMUTE", guild, user, moderator, timer)

    @LightningCog.listener()
    async def on_lightning_member_role_change(self, event):
        """Removes or adds the mute status to a member if the action was manually done"""
        record = await self.get_mod_config(event.guild.id)
        if not record or not record.mute_role_id:
            return

        # TODO: Handle temp mute role

        previously_muted = event.before._roles.has(record.mute_role_id)
        currently_muted = event.after._roles.has(record.mute_role_id)

        if previously_muted == currently_muted:
            return

        if event.moderator is None:
            # WARNING: This shouldn't happen, but this is a failsafe in case the guild hasn't given the
            # bot audit log perms. I don't like this solution, but this is ultimately the best solution.
            # The moderator who did the manual action can just claim the created infraction.
            event.moderator = self.bot.user

        if previously_muted is True and currently_muted is False:  # Role was removed
            async with self.bot.pool.acquire() as conn:
                check = await self.punishment_role_check(event.guild.id,
                                                         event.after.id, record.mute_role_id, connection=conn)
                if check is False:  # we are already unmuted
                    return

                await self.remove_punishment_role(event.guild.id, event.after.id, record.mute_role_id,
                                                  connection=conn)
                await self.update_last_mute(event.guild.id, event.after.id, connection=conn)

                if event.moderator.id != self.bot.user.id:
                    reason = modlogformats.action_format(event.moderator, "Mute role manually removed by")
                else:
                    reason = "Mute role manually removed"

                await self.log_manual_action(event.guild, event.after, event.moderator, "UNMUTE", reason=reason,
                                             connection=conn)

        if currently_muted is True and previously_muted is False:  # Role was added
            async with self.bot.pool.acquire() as conn:
                check = await self.punishment_role_check(event.guild.id,
                                                         event.after.id, record.mute_role_id, connection=conn)
                if check:  # we are already muted
                    return

                await self.add_punishment_role(event.guild.id, event.after.id, record.mute_role_id, connection=conn)

                if event.moderator.id != self.bot.user.id:
                    reason = modlogformats.action_format(event.moderator, "Mute role manually added by")
                else:
                    reason = "Mute role manually added"

                await self.log_manual_action(event.guild, event.after, event.moderator, "MUTE", reason=reason,
                                             connection=conn)

    # Automod
    # -------
    # TBH, this is mostly a bunch of listeners, but there's a command or two so it's staying in the same file.

    @command(hidden=True)
    async def raidmode(self, ctx: LightningContext) -> None:
        ...

    async def is_member_whitelisted(self, message) -> bool:
        """Check that tells whether a member is exempt from automod or not"""
        # TODO: Check against a generic set of moderator permissions.
        record = await self.bot.get_guild_bot_config(message.guild.id)
        if not record or record.permissions is None:
            return None

        if record.permissions.levels is None:
            level = CommandLevel.User
        else:
            roles = message.author._roles if hasattr(message.author, "_roles") else []
            level = record.permissions.levels.get_user_level(message.author.id, roles)

        if level == CommandLevel.Blocked:  # Blocked to commands, not ignored by automod
            return False

        return level.value >= CommandLevel.Trusted.value

    async def get_warn_count(self, guild_id: int, user_id: int) -> int:
        query = "SELECT COUNT(*) FROM infractions WHERE user_id=$1 AND guild_id=$2 AND action=$3;"
        rev = await self.bot.pool.fetchval(query, user_id, guild_id,
                                           modlogformats.ActionType.WARN.value)
        return rev or 0

    async def _kick_punishment(self, target):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        await target.kick(reason=reason)
        await self.log_manual_action(target, self.bot.user, "KICK", reason="Member triggered automod")

    async def _ban_punishment(self, target):
        reason = modlogformats.action_format(self.bot.user, reason="Automod triggered")
        await target.ban(reason=reason)
        await self.log_manual_action(target.guild, target, self.bot.user, "BAN", reason=reason)

    async def _delete_punishment(self, message):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    @LightningCog.listener("on_lightning_member_warn")
    async def handle_warn_punishments(self, event):
        record = await self.get_mod_config(event.guild.id)

        if not record or not record.warn_ban or not record.warn_kick:
            return

        count = await self.get_warn_count(event.guild.id, event.member.id)

        if record.warn_kick and record.warn_kick == count:
            await self._kick_punishment(event.member)

        if record.warn_ban and record.warn_ban <= count:
            await self._ban_punishment(event.member)

    @LightningCog.listener()
    async def on_message(self, message):
        if message.guild is None:  # DM Channels are exempt.
            return

        # TODO: Ignored channels
        check = await self.is_member_whitelisted(message)
        if check is True:
            return

        record = await self.get_mod_config(message.guild.id)
        if not record:
            return

        # Literally a way to punish nitro users :isabellejoy:
        if len(message.content) > 2000 and ModFlags.delete_longer_messages in record.flags:
            await self._delete_punishment(message)

        # More nitro punishments
        # Apparently some guilds are banning usage of stickers so this might be helpful for them.
        if len(message.stickers) != 0 and ModFlags.delete_stickers in record.flags:
            await self._delete_punishment(message)

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild: Union[PartialGuild, discord.Guild]) -> None:
        await self.get_mod_config.invalidate(guild.id)


async def setup(bot) -> None:
    await bot.add_cog(Mod(bot))
