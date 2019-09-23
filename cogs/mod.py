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

import discord
from discord.ext import commands
from utils.user_log import userlog
from utils.user_log import get_userlog, set_userlog, userlog_event_types
from utils.checks import is_staff_or_has_perms, has_staff_role, member_at_least_has_staff_role
from datetime import datetime
import json
# import asyncio
from utils.time import natural_timedelta
import io
from utils.paginator import Pages
from utils.converters import TargetMember, BadTarget
from utils.errors import TimersUnavailable

# Most Commands Taken From Robocop-NG. MIT Licensed
# https://github.com/aveao/robocop-ng/blob/master/cogs/mod.py


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


class ReasonTooLong(commands.UserInputError):
    pass


class NoMuteRole(commands.UserInputError):
    pass


class Mod(commands.Cog):
    """
    Most of these commands were taken from Robocop-NG's mod.py and moderately improved.

    Robocop-NG's mod.py is under the MIT license and is written by aveao / the ReSwitched team.

    See here for the license: https://github.com/aveao/robocop-ng/blob/master/LICENSE
    """
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    async def cog_command_error(self, ctx, error):
        if isinstance(error, ReasonTooLong):
            await ctx.safe_send(error)
        elif isinstance(error, NoMuteRole):
            return await ctx.safe_send(error)
        elif isinstance(error, BadTarget):
            return await ctx.safe_send(error)

    def mod_reason(self, ctx, reason: str):
        if reason:
            to_return = f"{ctx.author} (ID: {ctx.author.id}): {reason}"
        else:
            to_return = f"Action done by {ctx.author} (ID: {ctx.author.id})"
        if len(to_return) > 512:
            raise ReasonTooLong('Reason is too long!')
        return to_return

    async def log_send(self, ctx, message, **kwargs):
        query = """SELECT * FROM guild_mod_config
                   WHERE guild_id=$1;
                """
        async with self.bot.db.acquire() as con:
            ret = await con.fetchrow(query, ctx.guild.id)
        if ret:
            guild_config = json.loads(ret['log_channels'])
        else:
            guild_config = {}

        if "modlog_chan" in guild_config:
            try:
                log_channel = self.bot.get_channel(guild_config["modlog_chan"])
                await log_channel.send(content=message, **kwargs)
            except discord.Forbidden:
                pass

    async def purged_log_send(self, ctx, file_to_send):
        query = """SELECT * FROM guild_mod_config
                   WHERE guild_id=$1;
                """
        async with self.bot.db.acquire() as con:
            ret = await con.fetchrow(query, ctx.guild.id)
        if ret:
            guild_config = json.loads(ret['log_channels'])
        else:
            guild_config = {}

        if "modlog_chan" in guild_config:
            try:
                log_channel = self.bot.get_channel(guild_config["modlog_chan"])
                await log_channel.send(file=file_to_send)
            except discord.Forbidden:
                pass

    async def logid_send(self, guild_id: int, message):
        """Async Function to use a provided guild ID instead of relying
        on context (ctx). This is more for being used for Mod Log Cases"""
        query = """SELECT * FROM guild_mod_config
                   WHERE guild_id=$1;
                """
        async with self.bot.db.acquire() as con:
            ret = await con.fetchrow(query, guild_id)
        if ret:
            guild_config = json.loads(ret['log_channels'])
        else:
            guild_config = {}

        if "modlog_chan" in guild_config:
            try:
                log_channel = self.bot.get_channel(guild_config["modlog_chan"])
                msg = await log_channel.send(message)
                return msg
            except KeyError:
                pass

    async def set_user_restrictions(self, guild_id: int, user_id: int, role_id: int):
        query = """INSERT INTO user_restrictions (guild_id, user_id, role_id)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (guild_id, user_id, role_id)
                   DO UPDATE SET guild_id = EXCLUDED.guild_id,
                   role_id = EXCLUDED.role_id,
                   user_id = EXCLUDED.user_id;
                """
        con = await self.bot.db.acquire()
        try:
            await con.execute(query, guild_id, user_id, role_id)
        finally:
            await self.bot.db.release(con)

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

    async def add_modlog_entry(self, guild_id, action: str, mod, target, reason: str):
        """Adds a case to the mod log

        Arguments:
        --------------
        guild_id: `int`
            The guild id of where the action was done.
        action: `str`
            The type of action that was done.
            Actions can be one of the following: Ban, Kick, Mute, Unmute, Unban, Warn
        mod:
            The responsible moderator who did the action
        target:
            The member that got an action taken against them
        reason: `str`
            The reason why an action was taken
        """
        safe_name = await commands.clean_content().convert(self.bot, str(target))
        if action == "Ban":
            message = f"⛔ **Ban**: {mod.mention} banned "\
                      f"{target.mention} | {safe_name}\n"\
                      f"🏷 __User ID__: {target.id}\n"
        elif action == "Kick":
            message = f"👢 **Kick**: {mod.mention} kicked "\
                      f"{target.mention} | {safe_name}\n"\
                      f"🏷 __User ID__: {target.id}\n"
        # Send the initial message then edit it with our reason.
        if reason:
            message += f"✏️ __Reason__: \"{reason}\""
        else:
            message += f"*Responsible moderator* please add a reason to the case."\
                       f" `l.case "

    # @commands.Cog.listener()
    # async def on_member_ban(self, guild, user):
        # Wait for Audit Log to update
    #    await asyncio.sleep(0.5)
        # Cap off at 25 for safety measures
    #    async for entry in guild.audit_logs(limit=25, action=discord.AuditLogAction.ban):
    #        if entry.target == user:
    #            author = entry.user
    #            reason = entry.reason if entry.reason else ""
    #            break
        #  If author of the entry is the bot itself, don't log since
        #  this would've been already logged.
    #    if entry.target.id != self.bot.user.id:
    #        await self.add_modlog_entry(guild.id, "Ban", author, user, reason)

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
        aiofile = discord.File(aiostring, filename=f"{ctx.channel}_archive.txt")
        return aiofile

    @commands.guild_only()  # This isn't needed but w/e :shrugkitty:
    @commands.bot_has_permissions(kick_members=True)
    @is_staff_or_has_perms("Moderator", kick_members=True)
    @commands.command()
    async def kick(self, ctx, target: TargetMember, *, reason: str = ""):
        """Kicks a user.

        In order to use this command, you must either have
        Kick Members permission or a role that
        is assigned as a Moderator or above in the bot."""

        safe_name = await commands.clean_content().convert(ctx, str(target))

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
        chan_message = f"👢 **Kick**: {ctx.author.mention} kicked " \
                       f"{target.mention} | {safe_name}\n" \
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future" \
                            f", it is recommended to use " \
                            f"`{ctx.prefix}kick <user> [reason]`" \
                            f" as the reason is automatically sent to the user."
        await self.log_send(ctx, chan_message)

    @commands.guild_only()  # This isn't needed but w/e :shrugkitty:
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    @commands.command()
    async def ban(self, ctx, target: TargetMember, *, reason: str = ""):
        """Bans a user.

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""

        safe_name = await commands.clean_content().convert(ctx, str(target))

        dm_message = f"You were banned from {ctx.guild.name}."
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
        dm_message += "\n\nThis ban does not expire."
        dm_message += "\n\nIf you believe this to be in error, please message the staff."

        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents ban issues in cases where user blocked bot
            # or has DMs disabled
            pass

        await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, reason)}",
                            delete_message_days=0)
        await ctx.safe_send(f"{target} is now b&. 👍")
        chan_message = f"⛔ **Ban**: {ctx.author.mention} banned " \
                       f"{target.mention} | {safe_name}\n" \
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future" \
                            f", it is recommended to use `{ctx.prefix}ban <user> [reason]`" \
                            f" as the reason is automatically sent to the user."
        await self.log_send(ctx, chan_message)

    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True, ban_members=True)
    @has_staff_role("Helper")
    @commands.command()
    async def warn(self, ctx, target: TargetMember, *, reason: str = ""):
        """Warns a user.

        In order to use this command, you must have a role
        that is assigned as a Helper or above in the bot."""

        warn_count = await userlog(self.bot, ctx.guild, target.id,
                                   ctx.author, reason,
                                   "warns", target.name)

        msg = f"You were warned on {ctx.guild.name}."
        if reason:
            msg += " The given reason is: " + reason
        msg += f"\n\nThis is warn #{warn_count}."
        if warn_count == 2:
            msg += " __The next warn will automatically kick.__"
        if warn_count == 3:
            msg += "\n\nYou were kicked because of this warning. " \
                   "You can join again right away. " \
                   "Two more warnings will result in an automatic ban."
        if warn_count == 4:
            msg += "\n\nYou were kicked because of this warning. " \
                   "This is your final warning. " \
                   "You can join again, but " \
                   "**one more warn will result in a ban**."
        if warn_count == 5:
            msg += "\n\nYou were automatically banned due to five warnings."
            msg += "\nIf you believe this to be in error, please message the staff."
        try:
            await target.send(msg)
        except discord.errors.Forbidden:
            # Prevents log issues in cases where user blocked bot
            # or has DMs disabled
            pass
        if warn_count == 3 or warn_count == 4:
            opt_reason = f"[AutoKick] Reached {warn_count} warns. "
            if reason:
                opt_reason += f"{reason}"
            await ctx.guild.kick(target, reason=f"{self.mod_reason(ctx, opt_reason)}")
        if warn_count >= 5:  # just in case
            opt_reason = f"[AutoBan] Exceeded Warn Limit ({warn_count}). "
            if reason:
                opt_reason += f"{reason}"
            await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, opt_reason)}",
                                delete_message_days=0)
        await ctx.send(f"{target.mention} warned. "
                       f"User has {warn_count} warning(s).")
        safe_name = await commands.clean_content().convert(ctx, str(target))
        msg = f"⚠️ **Warned**: {ctx.author.mention} warned {target.mention}" \
              f" (warn #{warn_count}) | {safe_name}\n"

        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future" \
                   f", it is recommended to use `{ctx.prefix}warn <user> [reason]`" \
                   f" as the reason is automatically sent to the user."
        await self.log_send(ctx, msg)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True)
    @is_staff_or_has_perms("Moderator", manage_messages=True)
    @commands.command()
    async def purge(self, ctx, message_count: int, *, reason: str = ""):
        """Purges a channel's last x messages.

        In order to use this command, You must either have
        Manage Messages permission or a role that
        is assigned as a Moderator or above in the bot."""
        fi = await self.purged_txt(ctx, message_count)
        try:
            await ctx.channel.purge(limit=message_count)
        except Exception as e:
            self.bot.log.error(e)
            return await ctx.send('❌ Cannot purge messages!')

        msg = f'🗑️ **{message_count} messages purged** in {ctx.channel.mention} | {ctx.channel.name}\n'
        msg += f'Purger was {ctx.author.mention} | {ctx.author}\n'
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            pass
        await self.log_send(ctx, msg)
        await self.purged_log_send(ctx, fi)

    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    @commands.command(aliases=['slientban'])  # For some reason, I can't spell
    @is_staff_or_has_perms("Moderator", ban_members=True)
    async def silentban(self, ctx, target: discord.Member, *, reason: str = ""):
        """Bans a user without sending the reason to the member.

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""
        # Hedge-proofing the code
        if target == self.bot.user:  # Idiots
            return await ctx.send("You can't do mod actions on me.")
        elif target == ctx.author.id:
            return await ctx.send("You can't do mod actions on yourself.")
        elif await member_at_least_has_staff_role(ctx, target):
            return await ctx.send("I can't ban this user as "
                                  "they're a staff member.")

        safe_name = await commands.clean_content().convert(ctx, str(target))

        await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, reason)}",
                            delete_message_days=0)
        chan_message = f"⛔ **Silent Ban**: {ctx.author.mention} banned "\
                       f"{target.mention} | {safe_name}\n"\
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future"\
                            f", it is recommended to use `{ctx.prefix}ban <user> [reason]`"\
                            f" as the reason is automatically sent to the user."
        await self.log_send(ctx, chan_message)

    @commands.guild_only()
    @commands.command(aliases=["nick"])
    @is_staff_or_has_perms("Helper", manage_nicknames=True)
    async def nickname(self, ctx, target: discord.Member, *, nickname: str = ''):
        """Sets a user's nickname.

        In order to use this command, you must either have
        Manage Nicknames permission or a role that
        is assigned as a Helper or above in the bot."""
        try:
            await target.edit(nick=nickname)
        except discord.errors.Forbidden:
            await ctx.send("I can't change their nickname!")
            return

        await ctx.safe_send(f"Successfully changed {target.name}'s nickname.")

    async def get_mute_role(self, ctx):
        """Gets the guild's mute role if it exists"""
        query = """SELECT mute_role_id FROM guild_mod_config
                   WHERE guild_id=$1;
                """
        async with self.bot.db.acquire() as con:
            config = await con.fetchval(query, ctx.guild.id)
        if config:
            role = discord.utils.get(ctx.guild.roles, id=config)
            if role:
                return role
            else:
                raise NoMuteRole("The mute role that was configured "
                                 "seems to be deleted! "
                                 "Please setup a new mute role.")
        else:
            raise NoMuteRole("You do not have a mute role setup!")

    @commands.guild_only()
    @commands.command(aliases=['muteuser'])
    @commands.bot_has_permissions(manage_roles=True)
    @is_staff_or_has_perms("Moderator", manage_roles=True)
    async def mute(self, ctx, target: TargetMember, *, reason: str = ""):
        """Mutes a user.

        In order to use this command, you must either have
        Manage Roles permission or a role that
        is assigned as a Moderator or above in the bot."""
        role = await self.get_mute_role(ctx)

        safe_name = await commands.clean_content().convert(ctx, str(target))
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

        chan_message = f"🔇 **Muted**: {ctx.author.mention} muted "\
                       f"{target.mention} | {safe_name}\n"\
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future, "\
                            f"it is recommended to use `{ctx.prefix}mute <user> [reason]`"\
                            f" as the reason is automatically sent to the user."
        await self.set_user_restrictions(ctx.guild.id, target.id, role.id)
        await ctx.send(f"{target.mention} can no longer speak.")
        await self.log_send(ctx, chan_message)

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(manage_roles=True)
    @is_staff_or_has_perms("Moderator", manage_roles=True)
    async def unmute(self, ctx, target: discord.Member):
        """Unmutes a user.

        In order to use this command, you must either have
        Manage Roles permission or a role that
        is assigned as a Moderator or above in the bot."""
        role = await self.get_mute_role(ctx)
        await target.remove_roles(role, reason=f"{self.mod_reason(ctx, '[Unmute]')}")
        safe_name = await commands.clean_content().convert(ctx, str(target))
        chan_message = f"🔈 **Unmuted**: {ctx.author.mention} unmuted "\
                       f"{target.mention} | {safe_name}\n"\
                       f"🏷 __User ID__: {target.id}\n"
        await self.remove_user_restriction(ctx.guild.id, target.id, role.id)
        await ctx.send(f"{target.mention} can now speak again.")
        await self.log_send(ctx, chan_message)

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason: str = ""):
        """Unbans a user.

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""
        # A Re-implementation of the BannedMember converter taken from RoboDanny.
        # https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/mod.py
        ban_list = await ctx.guild.bans()
        try:
            member_id = int(user_id)
            entity = discord.utils.find(lambda u: u.user.id == member_id, ban_list)
        except ValueError:  # We'll fix this soon. It Just Works:tm: for now
            entity = discord.utils.find(lambda u: str(u.user) == user_id, ban_list)

        if entity is None:
            return await ctx.send("❌ Not a valid previously-banned member.")
            # This is a mess :p
        member = await self.bot.fetch_user(user_id)

        await ctx.guild.unban(member, reason=f"{self.mod_reason(ctx, reason)}")

        chan_message = f"⭕ **Unban**: {ctx.author.mention} unbanned "\
                       f"{member.mention} | {member}\n"\
                       f"🏷 __User ID__: {member.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future, "\
                            f"it is recommended to use `{ctx.prefix}unban <user_id> [reason]`."
        await ctx.send(f"{user_id} is now unbanned.")
        await self.log_send(ctx, chan_message)

    @commands.guild_only()
    @commands.command(aliases=['hackban'])
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    async def banid(self, ctx, user_id: int, *, reason: str = ""):
        """Bans a user by ID (hackban).

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""
        try:
            user = await self.bot.fetch_user(user_id)
        except discord.errors.NotFound:
            await ctx.send(f"❌ No user associated with ID `{user_id}`.")
        target_member = ctx.guild.get_member(user_id)
        # Hedge-proofing the code
        if user == self.bot.user:  # Idiots
            return await ctx.send("You can't do mod actions on me.")
        elif user == ctx.author.id:
            return await ctx.send("You can't do mod actions on yourself.")
        elif target_member and await member_at_least_has_staff_role(self, target_member):
            return await ctx.send("I can't ban this user as "
                                  "they're a staff member.")

        safe_name = await commands.clean_content().convert(ctx, str(user_id))

        await ctx.guild.ban(user,
                            reason=f"{self.mod_reason(ctx, reason)}",
                            delete_message_days=0)
        await ctx.send(f"{user} | {safe_name} is now b&. 👍")

        chan_message = f"⛔ **Hackban**: {ctx.author.mention} banned "\
                       f"{user.mention} | {safe_name}\n"\
                       f"🏷 __User ID__: {user_id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future"\
                            f", it is recommended to use "\
                            f"`{ctx.prefix}banid <user> [reason]`."
        await self.log_send(ctx, chan_message)

    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True)
    @is_staff_or_has_perms("Moderator", kick_members=True)
    @commands.command()
    async def silentkick(self, ctx, target: TargetMember, *, reason: str = ""):
        """Silently kicks a user. Does not DM a message to the target user.

        In order to use this command, you must either have
        Kick Members permission or a role that
        is assigned as a Moderator or above in the bot."""

        safe_name = await commands.clean_content().convert(ctx, str(target))

        await target.kick(reason=f"{self.mod_reason(ctx, reason)}")
        chan_message = f"👢 **Silent Kick**: {ctx.author.mention} kicked " \
                       f"{target.mention} | {safe_name}\n" \
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future" \
                            f", it is recommended to use " \
                            f"`{ctx.prefix}silentkick <user> [reason]`."
        await self.log_send(ctx, chan_message)

    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    @is_staff_or_has_perms("Moderator", ban_members=True)
    @commands.command(aliases=['tempban'])
    async def timeban(self, ctx, target: TargetMember,
                      duration: str, *, reason: str = ""):
        """Bans a user for a specified amount of time.

        In order to use this command, you must either have
        Ban Members permission or a role that
        is assigned as a Moderator or above in the bot."""
        expiry_timestamp = self.bot.parse_time(duration)
        expiry_datetime = datetime.utcfromtimestamp(expiry_timestamp)
        duration_text = self.bot.get_utc_timestamp(time_to=expiry_datetime,
                                                   include_to=True)
        timed_txt = natural_timedelta(expiry_datetime)
        duration_text = f"in {timed_txt} ({duration_text})"
        timer = self.bot.get_cog('PowersCronManagement')
        if not timer:
            raise TimersUnavailable
        ext = {"guild_id": ctx.guild.id, "user_id": target.id}
        await timer.add_job("timeban", datetime.utcnow(),
                            expiry_datetime, ext)

        safe_name = await commands.clean_content().convert(ctx, str(target))

        dm_message = f"You were banned from {ctx.guild.name}."
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
        dm_message += f"\n\nThis ban will expire {duration_text}."

        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents ban issues in cases where user blocked bot
            # or has DMs disabled
            pass
        reason_duration = self.bot.get_utc_timestamp(time_to=expiry_datetime,
                                                     include_to=True)
        if reason:
            opt_reason = f"{reason} (Timeban expires at {reason_duration})"
        else:
            opt_reason = f" (Timeban expires at {reason_duration})"
        await ctx.guild.ban(target, reason=f"{self.mod_reason(ctx, opt_reason)}",
                            delete_message_days=0)
        chan_message = f"⛔ **Timed Ban**: {ctx.author.mention} banned "\
                       f"{target.mention} for {duration_text} | {safe_name}\n"\
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += "Please add an explanation below. In the future"\
                            f", it is recommended to use `{ctx.prefix}timeban"\
                            " <target> <duration> [reason]`"\
                            " as the reason is automatically sent to the user."
        await ctx.send(f"{safe_name} is now b&. "
                       f"It will expire {duration_text}. 👍")
        await self.log_send(ctx, chan_message)

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(manage_roles=True)
    @is_staff_or_has_perms("Moderator", manage_roles=True)
    async def timemute(self, ctx, target: TargetMember,
                       duration: str, *, reason: str = ""):
        """Mutes a user for a specified amount of time.

        In order to use this command, you must either have
        Manage Roles permission or a role that
        is assigned as a Moderator or above in the bot."""
        role = await self.get_mute_role(ctx)
        expiry_timestamp = self.bot.parse_time(duration)
        expiry_datetime = datetime.utcfromtimestamp(expiry_timestamp)
        duration_text = self.bot.get_utc_timestamp(time_to=expiry_datetime,
                                                   include_to=True)
        timed_txt = natural_timedelta(expiry_datetime)
        duration_text = f"in {timed_txt} ({duration_text})"
        timer = self.bot.get_cog('PowersCronManagement')
        if not timer:
            raise TimersUnavailable
        ext = {"guild_id": ctx.guild.id, "user_id": target.id,
               "role_id": role.id}
        await timer.add_job("timed_restriction", datetime.utcnow(),
                            expiry_datetime, ext)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        dm_message = f"You were muted on {ctx.guild.name}!"
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
        dm_message += f"\n\nThis mute will expire {duration_text}."

        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents mute issues in cases where user blocked bot
            # or has DMs disabled
            pass
        reason_duration = self.bot.get_utc_timestamp(time_to=expiry_datetime,
                                                     include_to=True)
        if reason:
            opt_reason = f"{reason} (Timemute expires at {reason_duration})"
        else:
            opt_reason = f" (Timemute expires at {reason_duration})"

        await target.add_roles(role, reason=f"{self.mod_reason(ctx, opt_reason)}")

        chan_message = f"🔇 **Timed Mute**: {ctx.author.mention} muted "\
                       f"{target.mention} for {duration_text} | {safe_name}\n"\
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += "\nPlease add an explanation below. In the future, "\
                            f"it is recommended to use `{ctx.prefix}timemute <user> "\
                            "<duration> [reason]`"\
                            " as the reason is automatically sent to the user."
        await self.set_user_restrictions(ctx.guild.id, target.id, role.id)
        await ctx.send(f"{target.mention} can no longer speak. "
                       f"It will expire {duration_text}.")
        await self.log_send(ctx, chan_message)

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
        await channel.send(f"🔒 {channel.mention} is now locked.")

        # Define Safe Name so we don't mess this up (again)
        safe_name = await commands.clean_content().convert(ctx, str(ctx.author))
        log_message = f"🔒 **Lockdown** in {ctx.channel.mention} by {ctx.author.mention} | {safe_name}"
        await self.log_send(ctx, log_message)

    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @is_staff_or_has_perms("Admin", manage_channels=True)
    @commands.command(aliases=['hard-lock'])
    async def hlock(self, ctx, channel: discord.TextChannel = None):
        """Hard locks a channel.

        Sets the channel permissions as @everyone can't speak or see the channel.

        If no channel was mentioned, it hard locks the channel the command was used in.

        In order to use this command, You must either have
        Manage Channels permission or a role that
        is assigned as an Admin or above in the bot."""
        if not channel:
            channel = ctx.channel

        if channel.overwrites_for(ctx.guild.default_role).read_messages is False:
            await ctx.send(f"🔒 {channel.mention} is already hard locked. "
                           f"Use `{ctx.prefix}hard-unlock` to unlock the channel.")
            return

        await channel.set_permissions(ctx.guild.default_role, read_messages=False)
        await channel.send(f"🔒 {channel.mention} is now hard locked.")

        # Define Safe Name so we don't mess this up (again)
        safe_name = await commands.clean_content().convert(ctx, str(ctx.author))
        log_message = f"🔒 **Hard Lockdown** in {ctx.channel.mention} "\
                      f"by {ctx.author.mention} | {safe_name}"
        await self.log_send(ctx, log_message)

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
        await channel.send(f"🔓 {channel.mention} is now unlocked.")

        # Define Safe Name so we don't mess this up (again)
        safe_name = await commands.clean_content().convert(ctx, str(ctx.author))
        log_message = f"🔓 **Unlock** in {ctx.channel.mention} by {ctx.author.mention} | {safe_name}"
        await self.log_send(ctx, log_message)

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
        await channel.send(f"🔓 {channel.mention} is now unlocked.")

        # Define Safe Name so we don't mess this up (again)
        safe_name = await commands.clean_content().convert(ctx, str(ctx.author))
        log_message = f"🔓 **Hard Unlock** in {ctx.channel.mention} by {ctx.author.mention} | {safe_name}"
        await self.log_send(ctx, log_message)

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

    @commands.Cog.listener()
    async def on_timeban_job_complete(self, jobinfo):
        ext = json.loads(jobinfo['extra'])
        guid = self.bot.get_guild(ext['guild_id'])
        uid = await self.bot.fetch_user(ext['user_id'])
        await guid.unban(uid, reason="PowersCron: "
                         "Timed Ban Expired.")

    @commands.Cog.listener()
    async def on_timed_restriction_job_complete(self, jobinfo):
        ext = json.loads(jobinfo['extra'])
        guild = self.bot.get_guild(ext['guild_id'])
        user = guild.get_member(ext['user_id'])
        role = guild.get_role(ext['role_id'])
        await self.remove_user_restriction(guild.id,
                                           user.id,
                                           role.id)
        await user.remove_roles(role, reason="PowersCron: "
                                "Timed Restriction Expired.")

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
        embed.embed.color = 0x992d22
        return await embed.paginate()

    async def clear_event_from_id(self, uid: str, event_type, guild):
        userlog = await get_userlog(self.bot, guild)
        if uid not in userlog:
            return f"<@{uid}> has no {event_type}!"
        event_count = len(userlog[uid][event_type])
        if not event_count:
            return f"<@{uid}> has no {event_type}!"
        userlog[uid][event_type] = []
        await set_userlog(self.bot, guild, userlog)
        return f"<@{uid}> no longer has any {event_type}!"

    async def delete_event_from_id(self, uid: str, idx: int, event_type, guild):
        userlog = await get_userlog(self.bot, guild)
        if uid not in userlog:
            return f"<@{uid}> has no {event_type}!"
        event_count = len(userlog[uid][event_type])
        if not event_count:
            return f"<@{uid}> has no {event_type}!"
        if idx > event_count:
            return "Index is higher than " \
                   f"count ({event_count})!"
        if idx < 1:
            return "Index is below 1!"
        event = userlog[uid][event_type][idx - 1]
        event_name = userlog_event_types[event_type]
        embed = discord.Embed(color=discord.Color.dark_red(),
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
    async def userlog_cmd(self, ctx, target: discord.Member):
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
    @is_staff_or_has_perms("Helper", manage_messages=True)
    @commands.command()
    async def listwarnsid(self, ctx, target: int):
        """Lists all the warns for a user by ID.

        In order to use this command, You must either have
        Manage Messages permission or a role that
        is assigned as a Helper or above in the bot."""
        await self.get_userlog_embed_for_id(ctx, str(target), str(target),
                                            event="warns", guild=ctx.guild)

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command()
    async def clearwarns(self, ctx, target: discord.Member):
        """Clears all warns for a user.

        In order to use this command, You must either have
        Administrator permission or a role that
        is assigned as an Admin or above in the bot."""
        msg = await self.clear_event_from_id(str(target.id), "warns", guild=ctx.guild)
        await ctx.send(msg)
        safe_name = await commands.clean_content().convert(ctx, str(target))
        msg = f"🗑 **Cleared warns**: {ctx.author.mention} cleared" \
              f" all warns of {target.mention} | " \
              f"{safe_name}"
        await self.log_send(ctx, msg)

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command()
    async def clearwarnsid(self, ctx, target: int):
        """Clears all warns for a userid.

        In order to use this command, You must either have
        Administrator permission or a role that
        is assigned as an Admin or above in the bot."""
        msg = await self.clear_event_from_id(str(target), "warns", guild=ctx.guild)
        await ctx.send(msg)
        msg = f"🗑 **Cleared warns**: {ctx.author.mention} cleared" \
              f" all warns of <@{target}> "
        await self.log_send(ctx, msg)

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command(aliases=["deletewarn"])
    async def delwarn(self, ctx, target: discord.Member, idx: int):
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
            await ctx.send(f"{target.mention} has a {event_name} removed!")
            safe_name = await commands.clean_content().convert(ctx, str(target))
            msg = f"🗑 **Deleted {event_name}**: " \
                  f"{ctx.author.mention} removed " \
                  f"{event_name} {idx} from {target.mention} | " \
                  f"{safe_name}"
            await self.log_send(ctx, msg, embed=del_event)
        else:
            await ctx.send(del_event)

    @commands.guild_only()
    @is_staff_or_has_perms("Admin", administrator=True)
    @commands.command(aliases=["deletewarnid"])
    async def delwarnid(self, ctx, target: int, idx: int):
        """Removes a specific warn from a userid.

        In order to use this command, You must either have
        Administrator permission or a role that
        is assigned as an Admin or above in the bot."""
        del_event = await self.delete_event_from_id(str(target),
                                                    idx, "warns",
                                                    guild=ctx.guild)
        event_name = "warn"
        # This is hell.
        if isinstance(del_event, discord.Embed):
            await ctx.send(f"<@{target}> has a {event_name} removed!")
            msg = f"🗑 **Deleted {event_name}**: " \
                  f"{ctx.author.mention} removed " \
                  f"{event_name} {idx} from <@{target}> "
            await self.log_send(ctx, msg, embed=del_event)
        else:
            await ctx.send(del_event)


def setup(bot):
    bot.add_cog(Mod(bot))
