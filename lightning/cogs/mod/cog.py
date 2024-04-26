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

from __future__ import annotations

import contextlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Annotated, List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands
from unidecode import unidecode

from lightning import (CommandLevel, GuildContext, LightningBot, LightningCog,
                       LightningContext, cache, command, converters)
from lightning import flags as lflags
from lightning import group, hybrid_command
from lightning.cogs.mod.converters import BannedMember
from lightning.cogs.mod.flags import BaseModParser, PurgeFlags
from lightning.constants import COMMON_HOIST_CHARACTERS
from lightning.enums import ActionType
from lightning.errors import LightningError, MuteRoleError, TimersUnavailable
from lightning.events import InfractionEvent
from lightning.formatters import plural, truncate_text
from lightning.models import GuildModConfig, PartialGuild, Timer
from lightning.utils import helpers, modlogformats
from lightning.utils.checks import (has_channel_permissions,
                                    has_guild_permissions,
                                    hybrid_guild_permissions)
from lightning.utils.time import (FutureTime, get_utc_timestamp,
                                  natural_timedelta)

if TYPE_CHECKING:
    from lightning.cogs.reminders.cog import Reminders

    class ModContext(GuildContext):
        config: Optional[GuildModConfig]


confirmations = {"ban": "{target} was banned. \N{THUMBS UP SIGN}",
                 "timeban": "{target} was banned. \N{THUMBS UP SIGN} It will expire in {expiry}.",
                 "kick": "{target} was kicked. \N{OK HAND SIGN}",
                 "warn": "{target} was warned. ({count})",
                 "mute": "{target} can no longer speak.",
                 "timemute": "{target} can no longer speak. It will expire in {expiry}.",
                 "timeout": "{target} was put in timeout. It will expire in {expiry}.",
                 "unmute": "{target} can now speak again.",
                 "unban": "\N{OK HAND SIGN} {target} is now unbanned."}


class Mod(LightningCog, name="Moderation", required=["Configuration"]):
    """Moderation and server management commands."""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self.sanitize_appcommand = app_commands.ContextMenu(name="Sanitize Member", callback=self.sanitize_ac)
        bot.tree.add_command(self.sanitize_appcommand)

    @cache.cached('mod_config', cache.Strategy.lru)
    async def get_mod_config(self, guild_id: int) -> Optional[GuildModConfig]:
        query = "SELECT * FROM guild_mod_config WHERE guild_id=$1;"
        record = await self.bot.pool.fetchrow(query, guild_id)
        return GuildModConfig(record, self.bot) if record else None

    async def cog_check(self, ctx: LightningContext) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    async def cog_before_invoke(self, ctx: GuildContext) -> ModContext:
        record = await self.get_mod_config(ctx.guild.id)
        ctx.config = record
        return ctx  # type: ignore

    def format_reason(self, author, reason: Optional[str], *, action_text: Optional[str] = None) -> str:
        if action_text:
            return truncate_text(modlogformats.action_format(author, action_text, reason=reason), 512)
        else:
            return truncate_text(modlogformats.action_format(author, reason=reason), 512)

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

    async def log_manual_action(self, guild: discord.Guild, target: Union[discord.User, discord.Member], moderator,
                                action: Union[ActionType, str], *, timestamp=None,
                                reason: Optional[str] = None, **kwargs) -> None:
        # We need this for bulk actions
        connection = kwargs.pop('connection', self.bot.pool)

        timestamp = timestamp or discord.utils.utcnow()

        event = InfractionEvent(action, member=target, guild=guild, moderator=moderator, reason=reason, **kwargs)
        await event.action.add_infraction(connection)

        if not isinstance(action, ActionType):
            action = ActionType[str(action)]

        if str(action) == "TIMEMUTE":
            action = ActionType.MUTE

        if str(action) == "TIMEBAN":
            action = ActionType.BAN

        if event.action.expiry:
            event.action.expiry = natural_timedelta(event.action.expiry, source=timestamp)

        self.bot.dispatch(f"lightning_member_{str(action).lower()}", event)

    async def log_action(self, ctx: GuildContext, target, action: str, **kwargs) -> None:
        if ctx.kwargs.get('flags', None):
            reason = ctx.kwargs['flags'].reason
        else:
            reason = ctx.kwargs.get('reason', None)

        await self.log_manual_action(ctx.guild, target, ctx.author, action, timestamp=ctx.message.created_at,
                                     reason=reason, **kwargs)

    async def log_bulk_actions(self, ctx: GuildContext, targets: list, action: str, **kwargs) -> None:
        """Logs a bunch of actions"""
        async with self.bot.pool.acquire() as conn:
            for target in targets:
                await self.log_action(ctx, target, action, connection=conn, **kwargs)

    # TODO: Make this a decorator?
    async def confirm_and_log_action(self, ctx: GuildContext, target, action: str, **kwargs) -> None:
        duration_text = kwargs.pop("duration_text", None)
        warning_text = kwargs.pop("warning_text", None)

        await ctx.send(confirmations.get(action.lower(), "Done!").format(target=target, expiry=duration_text,
                                                                         count=warning_text))

        await self.log_action(ctx, target, action, **kwargs)

    @command(cls=lflags.FlagCommand, level=CommandLevel.Mod, parser=BaseModParser)
    @commands.bot_has_guild_permissions(kick_members=True)
    @has_guild_permissions(kick_members=True)
    async def kick(self, ctx: GuildContext, target: converters.TargetMember(fetch_user=False), *, flags) -> None:
        """Kicks a user from the server"""
        if not flags.nodm:  # No check is done here since we don't fetch users
            await helpers.dm_user(target, modlogformats.construct_dm_message(target, "kicked", "from",
                                  reason=flags.reason))

        await ctx.guild.kick(target, reason=self.format_reason(ctx.author, flags.reason))
        await self.confirm_and_log_action(ctx, target, "KICK")

    async def time_ban_user(self, ctx: GuildContext, target, moderator, reason, duration, *, dm_user=False,
                            delete_message_days=0) -> None:
        duration_text = f"{natural_timedelta(duration.dt, source=ctx.message.created_at)} ("\
                        f"{discord.utils.format_dt(duration.dt)})"

        cog: Optional[Reminders] = self.bot.get_cog('Reminders')  # type: ignore
        if not cog:
            raise TimersUnavailable

        tzinfo = await cog.get_user_tzinfo(ctx.author.id)
        created_timer = await cog.add_timer("timeban", ctx.message.created_at, duration.dt, guild_id=ctx.guild.id,
                                            user_id=target.id, mod_id=moderator.id, force_insert=True, timezone=tzinfo)

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
                                          expiry=duration.dt, timer=created_timer['id'])

    @lflags.add_flag("--nodm", "--no-dm", is_bool_flag=True,
                     help="Bot does not DM the user the reason for the action.")
    @lflags.add_flag("--delete-messages", converter=int, default=0,
                     help="Delete message history from a specified amount of days (Max 7)")
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    @command(cls=lflags.FlagCommand, level=CommandLevel.Mod, rest_attribute_name="reason",
             raise_bad_flag=False)
    async def ban(self, ctx: GuildContext,
                  target: Annotated[Union[discord.Member, discord.User], converters.TargetMember],
                  *, flags) -> None:
        """Bans a user from the server."""
        if flags['delete_messages'] < 0:
            raise commands.BadArgument("You can't delete a negative amount of messages.")

        reason = flags['reason']

        if not flags['nodm'] and isinstance(target, discord.Member):
            dm_message = modlogformats.construct_dm_message(target, "banned", "from", reason=reason)
            await helpers.dm_user(target, dm_message)

        await ctx.guild.ban(target, reason=self.format_reason(ctx.author, reason),
                            delete_message_days=min(flags['delete_messages'], 7))
        await self.confirm_and_log_action(ctx, target, "BAN")

    @command(cls=lflags.FlagCommand, level=CommandLevel.Mod, parser=BaseModParser)
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    async def bandel(self, ctx: GuildContext,
                     target: Annotated[Union[discord.Member, discord.User], converters.TargetMember],
                     *, flags) -> None:
        """Bans a user from the server and deletes 1 day worth of messages."""
        reason = flags['reason']

        if not flags['nodm'] and isinstance(target, discord.Member):
            dm_message = modlogformats.construct_dm_message(target, "banned", "from", reason=reason)
            await helpers.dm_user(target, dm_message)

        await ctx.guild.ban(target, reason=self.format_reason(ctx.author, reason),
                            delete_message_days=1)
        await self.confirm_and_log_action(ctx, target, "BAN")

    @hybrid_command(cls=lflags.HybridFlagCommand, level=CommandLevel.Mod, parser=BaseModParser)
    @app_commands.guild_only()
    @hybrid_guild_permissions(manage_messages=True)
    @app_commands.describe(target="The member to warn", reason="The reason for the warn")
    async def warn(self, ctx: GuildContext,
                   target: Union[discord.Member, discord.User] = commands.param(
                       converter=converters.TargetMember(fetch_user=False)),
                   *, flags) -> None:
        """Warns a member"""
        emoji = "\N{OPEN MAILBOX WITH LOWERED FLAG}"
        query = "SELECT COUNT(*) FROM infractions WHERE user_id=$1 AND guild_id=$2 AND action=$3;"
        warns = await self.bot.pool.fetchval(query, target.id, ctx.guild.id, ActionType.WARN.value) or 0

        if not flags.nodm and isinstance(target, discord.Member):
            dm_message = modlogformats.construct_dm_message(target, "warned", "in", reason=flags.reason,
                                                            ending=f"You now have {plural(warns + 1):warning}!\nTo view"
                                                                   f"your warns, use /mywarns in the server.")
            # ending="\n\nAdditional action may be taken against you if the server has set it up."
            indicator = await helpers.dm_user(target, dm_message)
            if indicator is True:
                emoji = "\N{OPEN MAILBOX WITH RAISED FLAG}"

        await self.confirm_and_log_action(ctx, target, "WARN", warning_text=f"{plural(warns + 1):warning} {emoji}")

    @hybrid_command(level=CommandLevel.Mod)
    @commands.bot_has_permissions(manage_messages=True)
    @hybrid_guild_permissions(manage_messages=True)
    @app_commands.guild_only()
    @app_commands.describe(search="The amount of messages to search")
    async def purge(self, ctx: GuildContext, search: commands.Range[int, 1, 300], *, flags: PurgeFlags) -> None:
        """Purges messages that meet a certain criteria"""
        predicates = []
        if flags.attachments:
            predicates.append(lambda x: len(x.attachments))

        if flags.user:
            predicates.append(lambda m: m.author.id == flags.user.id)

        if flags.bots:
            predicates.append(lambda m: m.author.bot)

        if search >= 150:
            resp = await ctx.confirm(f"Are you sure you want to purge {search} messages?", delete_after=True)
            if not resp:
                await ctx.send("Cancelled")
                return

        before = ctx.message if flags.before is None else discord.Object(id=flags.before)
        after = discord.Object(id=flags.after) if flags.after else None

        if ctx.interaction and ctx.interaction.response.is_done() is False:
            await ctx.defer()

        try:
            purged = await ctx.channel.purge(limit=search,
                                             before=before,
                                             after=after,
                                             check=lambda m: all(p(m) for p in predicates))
        except discord.Forbidden:
            raise commands.MissingPermissions([])
        except discord.HTTPException as e:
            raise LightningError(f"Error: {e} (try a smaller message search?)") from e

        spam = Counter(str(m.author) for m in purged)
        dcount = len(purged)
        messages = [f"**{plural(dcount):message} purged**"]
        if dcount:
            messages.append('')
            spam = sorted(spam.items(), key=lambda m: m[1], reverse=True)
            messages.extend(f'{name}: {count}' for name, count in spam)
        msg = '\n'.join(messages)
        await ctx.send(msg, delete_after=40)

    def can_timeout(self, ctx: ModContext, duration: datetime):
        me = ctx.message.guild.me
        return bool(
            ctx.message.channel.permissions_for(me).moderate_members
            and duration <= (ctx.message.created_at + timedelta(days=28))  # noqa: W503
        )

    async def get_mute_role(self, ctx: ModContext) -> discord.Role:
        """Gets the guild's mute role if it exists"""
        if not ctx.config:
            raise MuteRoleError("You do not have a mute role set.")

        return ctx.config.get_mute_role()

    async def timeout_member(self, ctx: ModContext, target: discord.Member, reason: str, duration: FutureTime,
                             *, dm_user=False):
        timer: Optional[Reminders] = self.bot.get_cog('Reminders')  # type: ignore
        if not timer:
            raise TimersUnavailable

        self.bot.ignore_modlog_event(ctx.guild.id, "on_lightning_member_timeout", f"{target.id}")

        try:
            await target.edit(timed_out_until=duration.dt, reason=self.format_reason(ctx.author, reason))
        except discord.HTTPException as e:
            raise MuteRoleError(f"Unable to timeout {target} ({str(e)})")

        rec = await timer.add_timer("timeout", ctx.message.created_at, duration.dt, force_insert=True,
                                    timezone=duration.dt.tzinfo)

        dt_text = discord.utils.format_dt(duration.dt)
        if dm_user:
            msg = modlogformats.construct_dm_message(target, "timed out", "in", reason=reason,
                                                     ending="\n\nThis timeout will expire at "
                                                            f"{dt_text}.")
            await helpers.dm_user(target, msg)

        await self.confirm_and_log_action(ctx, target, "TIMEOUT", duration_text=dt_text, expiry=duration.dt,
                                          timer=rec['id'])

    async def time_mute_user(self, ctx: ModContext, target: Union[discord.User, discord.Member], reason: str,
                             duration: FutureTime, *, dm_user=False):
        eligible = self.can_timeout(ctx, duration.dt)
        if not ctx.config and isinstance(target, discord.Member) and eligible is True:
            await self.timeout_member(ctx, target, reason, duration, dm_user=dm_user)
            return

        try:
            role = await self.get_mute_role(ctx)
        except MuteRoleError as e:
            if eligible and isinstance(target, discord.Member):
                await self.timeout_member(ctx, target, reason, duration, dm_user=dm_user)
                return
            raise e

        duration_text = f"{natural_timedelta(duration.dt, source=ctx.message.created_at)} ("\
                        f"{discord.utils.format_dt(duration.dt)})"

        timer: Optional[Reminders] = self.bot.get_cog('Reminders')
        if not timer:
            raise TimersUnavailable

        tzinfo = await timer.get_user_tzinfo(ctx.author.id)
        created_timer = await timer.add_timer("timemute", ctx.message.created_at,
                                              duration.dt, guild_id=ctx.guild.id, user_id=target.id, role_id=role.id,
                                              mod_id=ctx.author.id, force_insert=True, timezone=tzinfo)

        if isinstance(target, discord.Member):
            if dm_user:
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
                                          timer=created_timer['id'])

    @command(cls=lflags.HybridFlagCommand, level=CommandLevel.Mod, parser=BaseModParser)
    @commands.bot_has_guild_permissions(manage_roles=True, moderate_members=True)
    @hybrid_guild_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def mute(self, ctx: ModContext, target: converters.TargetMember, *, flags) -> None:
        """Permanently mutes a user"""
        role = await self.get_mute_role(ctx)

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

    async def update_last_mute(self, guild_id, user_id, *, action: int = 6, connection=None):
        connection = connection or self.bot.pool
        query = """SELECT id FROM infractions
                   WHERE guild_id=$1
                   AND user_id=$2
                   AND action=$3
                   ORDER BY created_at DESC
                   LIMIT 1;
                """
        val = await connection.fetchval(query, guild_id, user_id, action)

        query = """UPDATE infractions
                   SET active=false
                   WHERE guild_id=$1 AND id=$2;
                """
        return await connection.execute(query, guild_id, val)

    @hybrid_command(level=CommandLevel.Mod)
    @app_commands.describe(target="The member to unmute", reason="The reason for the unmute")
    @commands.bot_has_guild_permissions(manage_roles=True, moderate_members=True)
    @hybrid_guild_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def unmute(self, ctx: ModContext, target: discord.Member, *,
                     reason: Optional[str]) -> None:
        """Unmutes a user"""
        if target.is_timed_out():
            await target.edit(timed_out_until=None, reason=self.format_reason(ctx.author, reason))
            await ctx.send(f"Removed {target} from timeout.")
            return

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

    @command(level=CommandLevel.Mod, cls=lflags.HybridFlagCommand, parser=BaseModParser)
    @commands.bot_has_guild_permissions(moderate_members=True)
    @hybrid_guild_permissions(moderate_members=True)
    @app_commands.describe(target="The member to timeout", duration="The duration for the timeout (max 28 days)",
                           reason="The reason for the timeout")
    async def timeout(self, ctx: ModContext,
                      target: converters.TargetMember(fetch_user=False), duration: FutureTime,
                      *, flags):
        """Timeout a member"""
        if not self.can_timeout(ctx, duration.dt):
            await ctx.send("Timeouts only support up to 28 days. "
                           f"Please use a lower duration or use `{ctx.clean_prefix}timemute`",
                           ephemeral=True)
            return

        await self.timeout_member(ctx, target, flags['reason'], duration, dm_user=not flags['nodm'])

    @hybrid_command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(moderate_members=True)
    @hybrid_guild_permissions(moderate_members=True)
    @app_commands.describe(target="The member to remove from timeout", reason="The reason for the untimeout")
    @app_commands.guild_only()
    async def untimeout(self, ctx: ModContext, target: discord.Member, *, reason: Optional[str] = None):
        """Removes a member from time out"""
        if not target.is_timed_out():
            await ctx.send(f"{target.mention} is not in time out!", ephemeral=True)
            return

        await target.edit(timed_out_until=None, reason=self.format_reason(ctx.author, reason))

        await ctx.send(f"Removed {target} from time out!")

    @command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    async def unban(self, ctx: GuildContext, member: discord.BanEntry = commands.param(
                    converter=BannedMember), *, reason: Optional[str] = None) -> None:
        """Unbans a user

        You can pass either the ID of the banned member, the mention of the member, or the Name#Discrim \
        combination of the member. The member's ID is easier to use."""
        await ctx.guild.unban(member.user, reason=self.format_reason(ctx.author, reason))
        await self.confirm_and_log_action(ctx, member.user, "UNBAN")

    @command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(ban_members=True)
    @has_guild_permissions(ban_members=True)
    async def massban(self, ctx: GuildContext, members: commands.Greedy[converters.TargetMember],
                      *, reason: str) -> None:
        """Mass bans users from the server"""
        confirm = await ctx.confirm(f"Are you sure you want to ban {plural(len(members)):member}?\n"
                                    "They will **not** be notified about being banned!")
        if not confirm:
            return

        reason = self.format_reason(ctx.author.id, reason, action_text="Ban done by")

        async with self.bot.pool.acquire() as con:
            for member in members:
                await ctx.guild.ban(member, delete_message_days=0, reason=reason)
                await self.log_action(ctx, member, "BAN", connection=con)

    @commands.bot_has_guild_permissions(ban_members=True)
    @command(cls=lflags.HybridFlagCommand, aliases=['tempban'], level=CommandLevel.Mod, parser=BaseModParser)
    @hybrid_guild_permissions(ban_members=True)
    @app_commands.describe(target="The member to ban",
                           duration="The duration for the ban",
                           reason="The reason for the timed ban")
    @app_commands.guild_only()
    async def timeban(self, ctx: GuildContext, target: converters.TargetMember,
                      duration: FutureTime, *, flags) -> None:
        """Bans a user for a specified amount of time.

        The duration can be a short time format such as "30d", \
        a more human duration format such as "until Monday at 7PM", \
        or a more concrete time format such as "2020-12-31"."""
        await self.time_ban_user(ctx, target, ctx.author, flags['reason'], duration, dm_user=not flags['nodm'])

    @command(aliases=['tempmute'], level=CommandLevel.Mod, cls=lflags.HybridFlagCommand, parser=BaseModParser)
    @commands.bot_has_guild_permissions(manage_roles=True, moderate_members=True)
    @hybrid_guild_permissions(moderate_members=True)
    @app_commands.describe(target="The member to mute",
                           duration="The duration for the mute",
                           reason="The reason for the mute")
    @app_commands.guild_only()
    async def timemute(self, ctx: ModContext, target: converters.TargetMember,
                       duration: FutureTime, *, flags) -> None:
        """Mutes a user for a specified amount of time.

        The duration can be a short time format such as "30d", \
        a more human duration format such as "until Monday at 7PM", \
        or a more concrete time format such as "2020-12-31"."""
        await self.time_mute_user(ctx, target, flags['reason'], duration, dm_user=not flags['nodm'])

    @commands.bot_has_permissions(manage_channels=True)
    @has_guild_permissions(manage_channels=True)
    @group(aliases=['lockdown'], invoke_without_command=True, level=CommandLevel.Mod)
    async def lock(self, ctx: GuildContext, channel: discord.TextChannel = commands.CurrentChannel) -> None:
        """Locks down the channel mentioned.

        Sets the channel permissions as @everyone can't send messages.

        If no channel was mentioned, it locks the channel the command was used in."""
        if channel == ctx.channel:
            confirm = await ctx.confirm("Are you sure you want to lock down this channel?")

            if not confirm:
                return

        if channel.overwrites_for(ctx.guild.default_role).send_messages is False:
            await ctx.send(f"🔒 {channel.mention} is already locked down. "
                           f"Use `{ctx.prefix}unlock` to unlock.")
            return

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = False
        overwrites.add_reactions = False
        overwrites.create_public_threads = False
        overwrites.create_private_threads = False
        reason = modlogformats.action_format(ctx.author, "Lockdown done by")

        try:
            await channel.set_permissions(ctx.guild.default_role, reason=reason, overwrite=overwrites)
        except discord.Forbidden as e:
            # Thanks Onboarding!
            await ctx.send(f"Unable to lock that channel! `{str(e)}`")
            return

        # Bot permissions
        await channel.set_permissions(ctx.me, reason=reason, send_messages=True, manage_channels=True)
        await ctx.send(f"\N{LOCK} {channel.mention} is now locked.")

    @lock.command(name="thread", level=CommandLevel.Mod)
    @has_channel_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def lock_thread(self, ctx: GuildContext, thread: discord.Thread = commands.CurrentChannel):
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
    @command(level=CommandLevel.Mod)
    async def unlock(self, ctx: GuildContext,
                     channel: discord.TextChannel = commands.CurrentChannel) -> None:
        """Unlocks the channel mentioned.

        If no channel was mentioned, it unlocks the channel the command was used in."""
        if channel.overwrites_for(ctx.guild.default_role).send_messages is None:
            await ctx.send(f"🔓 {channel.mention} is already unlocked.")
            return

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = None
        overwrites.add_reactions = None
        overwrites.create_private_threads = None
        overwrites.create_public_threads = None

        reason = modlogformats.action_format(ctx.author, "Lockdown removed by")
        await channel.set_permissions(ctx.guild.default_role, reason=reason, overwrite=overwrites)
        await ctx.send(f"🔓 {channel.mention} is now unlocked.")

    @has_guild_permissions(manage_messages=True)
    @command(level=CommandLevel.Mod)
    async def clean(self, ctx: GuildContext, search: int = 100,
                    channel: discord.TextChannel = commands.CurrentChannel) -> None:
        """Cleans the bot's messages from the channel specified.

        If no channel is specified, the bot deletes its \
        messages from the channel the command was run in.

        If a search number is specified, it will search \
        that many messages from the bot in the specified channel and clean them.
        """
        if (search > 100):
            raise commands.BadArgument("Cannot purge more than 100 messages.")

        has_perms = ctx.channel.permissions_for(ctx.guild.me).manage_messages
        await channel.purge(limit=search, check=lambda b: b.author.id == ctx.bot.user.id,
                            before=ctx.message.created_at,
                            after=datetime.now(timezone.utc) - timedelta(days=14),
                            bulk=has_perms)

        await ctx.send("\N{OK HAND SIGN}", delete_after=15)

    async def dehoist_member(self, member: discord.Member, moderator, characters: list, *, normalize: bool = False):
        if member.discriminator == 0 and member.display_name == member.name:
            # This is already compliant
            return

        old_nick = unidecode(member.display_name) if normalize else member.display_name
        new_nick = old_nick

        for char in old_nick:
            if char not in characters:
                break

            new_nick = new_nick[1:].lstrip()

        if len(new_nick) == 0:
            new_nick = "don't hoist"

        if old_nick == new_nick and not normalize:
            return False

        if old_nick == new_nick and member.nick is None:
            return False

        await member.edit(nick=new_nick, reason=self.format_reason(moderator, None, action_text="Dehoist done by"))

        if old_nick != new_nick:
            return True

    @hybrid_command(level=CommandLevel.Mod)
    @hybrid_guild_permissions(manage_guild=True, manage_nicknames=True)
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @commands.cooldown(1, 300.0, commands.BucketType.guild)
    @app_commands.guild_only()
    async def dehoist(self, ctx: GuildContext, character: Optional[str]):
        """Dehoists members with an optional specified character in the beginning of their name"""
        char: List[str] = [character] if character else COMMON_HOIST_CHARACTERS
        dehoists = []
        failed_dehoist = []

        async with ctx.typing():
            for member in ctx.guild.members:
                try:
                    i = await self.dehoist_member(member, ctx.author, char)
                except discord.HTTPException:
                    failed_dehoist.append(member)
                    continue

                if i:
                    dehoists.append(member)

        await ctx.send(f"Dehoisted {len(dehoists)}/{len(ctx.guild.members)}\n{len(failed_dehoist)} failed.")

    @hybrid_command(level=CommandLevel.Mod)
    @commands.bot_has_guild_permissions(manage_nicknames=True)
    @hybrid_guild_permissions(manage_nicknames=True)
    @app_commands.guild_only()
    async def normalize(self, ctx: GuildContext, member: discord.Member):
        """Transliterates a member's name into ASCII"""
        normalized = unidecode(member.display_name)
        try:
            await member.edit(nick=normalized, reason=self.format_reason(ctx.author, None,
                                                                         action_text="Normalize done by"))
        except discord.HTTPException as e:
            await ctx.send(f"I had an issue trying to normalize their name {str(e)}")
            return

        await ctx.send(f"Normalized {member.mention}")

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_nicknames=True)
    async def sanitize_ac(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await self.dehoist_member(member, interaction.user, COMMON_HOIST_CHARACTERS, normalize=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"I was unable to sanitize {member.mention}. ({str(e)})")
            return

        await interaction.response.send_message(f"Sanitized {member.mention}", ephemeral=True)

    @LightningCog.listener()
    async def on_lightning_timeban_complete(self, timer: Timer):
        assert timer.extra is not None

        guild = self.bot.get_guild(timer.extra['guild_id'])
        if guild is None:
            # Bot was kicked.
            return

        try:
            user = await self.bot.fetch_user(timer.extra['user_id'])
        except discord.HTTPException:
            user = helpers.UserObject(id=timer.extra['user_id'])

        moderator = guild.get_member(timer.extra['mod_id']) or helpers.UserObject(id=timer.extra['mod_id'])

        reason = f"Timed ban made by {modlogformats.base_user_format(moderator)} at {timer.created_at} expired"
        await guild.unban(user, reason=reason)
        self.bot.dispatch("lightning_timed_moderation_action_done", "UNBAN", guild, user, moderator, timer)

    @LightningCog.listener()
    async def on_lightning_timemute_complete(self, timer: Timer):
        assert timer.extra is not None

        async with self.bot.pool.acquire() as connection:
            if await self.punishment_role_check(timer.extra['guild_id'],
                                                timer.extra['user_id'],
                                                timer.extra['role_id'], connection=connection) is False:
                return

            await self.remove_punishment_role(timer.extra['guild_id'], timer.extra['user_id'],
                                              timer.extra['role_id'], connection=connection)

        guild = self.bot.get_guild(timer.extra['guild_id'])
        if guild is None:
            # Bot was kicked.
            return

        moderator = guild.get_member(timer.extra['mod_id']) or helpers.UserObject(timer.extra['mod_id'])

        role = guild.get_role(timer.extra['role_id'])
        if role is None:
            # Role was deleted or something.
            return

        user = guild.get_member(timer.extra['user_id'])
        if user is None:
            # User left probably...
            user = helpers.UserObject(timer.extra['user_id'])
        else:
            reason = f"Timed mute made by {modlogformats.base_user_format(moderator)} at "\
                     f"{get_utc_timestamp(timer.created_at)} expired"
            # I think I'll intentionally let it raise an error if bot missing perms or w/e...
            await user.remove_roles(role, reason=reason)

        self.bot.dispatch("lightning_timed_moderation_action_done", "UNMUTE", guild, user, moderator, timer)

    @LightningCog.listener()
    async def on_lightning_member_role_change(self, event):
        """Removes or adds the mute status to a member if the action was manually done"""
        record = await self.get_mod_config(event.guild.id)
        if not record or not record.mute_role_id:
            return

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

    @LightningCog.listener()
    async def on_lightning_guild_remove(self, guild: Union[PartialGuild, discord.Guild]) -> None:
        await self.get_mod_config.invalidate(guild.id)

    # Role state listeners
    @LightningCog.listener('on_member_join')
    async def reapply_role_state_on_join(self, member: discord.Member):
        query = "SELECT punishment_roles FROM roles WHERE guild_id=$1 AND user_id=$2;"
        record = await self.bot.pool.fetchval(query, member.guild.id, member.id)
        if not record:
            return

        with contextlib.suppress(discord.HTTPException):
            await member.add_roles(*[discord.Object(id=i) for i in record], reason="Role persist")

    @LightningCog.listener('on_guild_role_delete')
    async def remove_role_from_role_states_on_delete(self, role: discord.Role):
        query = "SELECT COUNT(*) FROM roles WHERE guild_id=$1 AND $2 = ANY(punishment_roles);"
        check = await self.bot.pool.fetchval(query, role.guild.id, role.id)
        if not check:
            return

        query = "UPDATE roles SET punishment_roles = array_remove(punishment_roles, $1) WHERE guild_id=$2;"
        await self.bot.pool.execute(query, role.id, role.guild.id)
