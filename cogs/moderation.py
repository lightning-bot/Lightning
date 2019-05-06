# kirigiri - A discord bot.
# Copyright (C) 2018 - Valentijn "noirscape" V.
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
# In addition, the additional clauses 7b and 7c are in effect for this program.
#
# b) Requiring preservation of specified reasonable legal notices or
# author attributions in that material or in the Appropriate Legal
# Notices displayed by works containing it; or
#
# c) Prohibiting misrepresentation of the origin of that material, or
# requiring that modified versions of such material be marked in
# reasonable ways as different from the original version; or

import discord
from discord.ext import commands
from discord.ext.commands import Cog
import db.per_guild_config
from db.user_log import userlog
from database import Config
from database import Restrictions
from typing import Union
import db.mod_check
import datetime
import asyncio
import traceback

## Most commands here taken from robocop-ngs mod.py
# https://github.com/aveao/robocop-ng/blob/master/cogs/mod.py
# robocop-ng is MIT licensed

class Moderation(commands.Cog):
    """
    Moderation cog.

    Most of these commands were taken from robocop-ngs mod.py and slightly adapted.

    robcop-ngs mod.py is under the MIT license and is written by aveao / the ReSwitched team.

    See here for the license: https://github.com/aveao/robocop-ng/blob/master/LICENSE
    """

    def __init__(self, bot):
        self.bot = bot
        self.bot.log.info(f'{self.qualified_name} loaded')
        
    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True


    def check_if_target_has_any_roles(self, member: discord.Member, roles_list: list):
        return any(role in member.roles for role in roles_list)

    async def cog_before_invoke(self, ctx):
        if db.per_guild_config.exist_guild_config(ctx.guild, "config"):
            ctx.guild_config = db.per_guild_config.get_guild_config(ctx.guild, "config")
        else:
            ctx.guild_config = {}

    async def cog_after_invoke(self, ctx):
        db.per_guild_config.write_guild_config(ctx.guild, ctx.guild_config, "config")


    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    @commands.command()
    async def kick(self, ctx, target: discord.Member, *, reason: str = ""):
        """Kicks a user.
        
        Moderator and Admin only.
        """
        # Hedge-proofing the code
        if target == self.bot.user:  # Idiots
            return await ctx.send("You can't do mod actions on me.")
        elif target == ctx.author:
            return await ctx.send("You can't do mod actions on yourself.")
        elif db.mod_check.member_at_least_has_staff_role(target):
            return await ctx.send("I can't kick this user as "
                                  "they're a staff member.")

        userlog(ctx.guild, target.id, ctx.author, reason, "kicks", target.name)

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
        await ctx.send(f"{target} has been kicked. 👌 ")
        await target.kick(reason=f"{ctx.author}, reason: {reason}")
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

        if "log_channel" in ctx.guild_config:
            try:
                log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
                await log_channel.send(chan_message)
            except:
                pass  # w/e, dumbasses forgot to set it properly.

    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    @commands.command()
    async def ban(self, ctx, target: discord.Member, *, reason: str = ""):
        """Bans a user, staff only."""
        # Hedge-proofing the code
        if target == self.bot.user:  # Idiots
            return await ctx.send("You can't do mod actions on me.")
        elif target == ctx.author:
            return await ctx.send("You can't do mod actions on yourself.")
        elif db.mod_check.member_at_least_has_staff_role(target):
            return await ctx.send("I can't ban this user as "
                                  "they're a staff member.")

        userlog(ctx.guild, target.id, ctx.author, reason, "bans", target.name)

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

        await target.ban(reason=f"{ctx.author}, reason: {reason}",
                         delete_message_days=0)
        chan_message = f"⛔ **Ban**: {ctx.author.mention} banned " \
                       f"{target.mention} | {safe_name}\n" \
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future" \
                            f", it is recommended to use `{ctx.prefix}ban <user> [reason]`" \
                            f" as the reason is automatically sent to the user."

        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(chan_message)
                await ctx.send(f"{safe_name} is now b&. 👍")
            except:
                pass  # w/e, dumbasses forgot to set send perms properly.

    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True, ban_members=True)
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    @commands.command()
    async def warn(self, ctx, target: discord.Member, *, reason: str = ""):
        """Warns a user, staff only."""
        # Hedge-proofing the code
        if target == self.bot.user:  # Idiots
            return await ctx.send("You can't do mod actions on me.")
        elif target == ctx.author:
            return await ctx.send("You can't do mod actions on yourself.")
        elif db.mod_check.member_at_least_has_staff_role(target):
            return await ctx.send("I can't warn this user as "
                                  "they're a staff member.")

        warn_count = userlog(ctx.guild, target.id, ctx.author, reason,
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
            await target.kick()
        if warn_count >= 5:  # just in case
            await target.ban(reason="exceeded warn limit",
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

        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(msg)
            except:
                pass  # Whatever dumbasses forgot to set perms properly


    @commands.guild_only()
    @commands.bot_has_permissions(manage_messages=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    @commands.command()
    async def purge(self, ctx, message_count: int, *, reason: str = ""):
        """Purge a channels last x messages. Moderators and Admins only."""
        try:
            await ctx.channel.purge(limit=message_count)
        except Exception as e:
            print(e)
            return await ctx.send('Cannot purge messages!')

        msg = f'🗑️ **{message_count} messages purged** in {ctx.channel.mention} | {ctx.channel.name} | {ctx.channel.id} \n'
        msg += f'Purger was {ctx.author.mention} | {ctx.author.name}#{ctx.author.discriminator} | {ctx.author.id} \n'
        if reason:
            msg += f"✏️ __Reason__: \"{reason}\""
        else:
            msg += f"\nPlease add an explanation below. In the future" \
                   f", it is recommended to use `{ctx.prefix}purge <message_count> [reason]`" \
                   f" for documentation purposes."

        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(msg)
            except:
                pass  # Whatever dumbasses forgot to set perms properly

    @commands.guild_only()
    @commands.bot_has_permissions(ban_members=True)
    @commands.command(aliases=['slientban']) # For some reason, I can't spell
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def silentban(self, ctx, target: discord.Member, *, reason: str = ""):
        """Silently bans a user. moderators & admin only."""        
        # Hedge-proofing the code
        if target == self.bot.user:  # Idiots
            return await ctx.send("You can't do mod actions on me.")
        elif target == ctx.author.id:
            return await ctx.send("You can't do mod actions on yourself.")
        elif db.mod_check.member_at_least_has_staff_role(target):
            return await ctx.send("I can't ban this user as "
                                  "they're a staff member.")

        userlog(ctx.guild, target.id, ctx.author, reason, "bans", target.name)
        safe_name = await commands.clean_content().convert(ctx, str(target))

        await target.ban(reason=f"{ctx.author}, reason: {reason}",
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
 
        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(chan_message)
            except:
                pass  # w/e, dumbasses forgot to set send perms properly.

    @commands.guild_only()
    @commands.command(aliases=["nick"])
    @db.mod_check.check_if_at_least_has_staff_role("Helper")
    async def nickname(self, ctx, target: discord.Member, *, nick: str = ''):
        """Sets a user's nickname, staff only.
        Useful for servers enforcing a nickname policy or manually applying nicknames."""

        try:
            await target.edit(nick=nick, reason=str(ctx.author))
        except discord.errors.Forbidden:
                await ctx.send("<:noblobaww:561618920096792596>  I can't change their nickname!")
                return
        await ctx.send(f"Successfully set nickname to {nick}.")

        safe_name = await commands.clean_content().convert(ctx, str(target))

        chan_message = f"📇 **Nickname Change**: {ctx.author.mention} changed "\
                       f"{target.mention}'s nickname to"\
                       f' "{nick}"  | {safe_name}\n'

        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(chan_message)
            except:
                pass  # w/e, dumbasses forgot to set send perms properly.

    @commands.guild_only()
    @commands.command(aliases=['muteuser'])
    @commands.bot_has_permissions(manage_roles=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def mute(self, ctx, target: discord.Member, *, reason: str = ""):
        """Mutes a user, Moderator+ only."""
        # Hedge-proofing the code
        if target == self.bot.user:  # Idiots
            return await ctx.send("You can't do mod actions on me.")
        elif target == ctx.author.id:
            return await ctx.send("You can't do mod actions on yourself.")
        elif db.mod_check.member_at_least_has_staff_role(target):
            return await ctx.send("I can't mute this user as "
                                  "they're a staff member.")

        # Rev up that chemotherapy, cause this part is cancer.
        session = self.bot.db.dbsession() # Check to see if mute role is setup
        try:
            role_id = session.query(Config).filter_by(guild_id=ctx.guild.id).one()
            role = discord.Object(id=role_id.mute_role_id)
        except:
            role_id = None
            return await ctx.send("❌ You need to setup a mute role.")

        userlog(ctx.guild, target.id, ctx.author, reason, "mutes", target.name)
        safe_name = await commands.clean_content().convert(ctx, str(target)) # Let's not make the mistake
        dm_message = f"You were muted on {ctx.guild.name}!"
        if reason:
            dm_message += f" The given reason is: \"{reason}\"."
        try:
            await target.send(dm_message)
        except discord.errors.Forbidden:
            # Prevents issues in cases where user blocked bot
            # or has DMs disabled
            pass

        await target.add_roles(role, reason=str(ctx.author))

        chan_message = f"🔇 **Muted**: {ctx.author.mention} muted "\
                       f"{target.mention} | {safe_name}\n"\
                       f"🏷 __User ID__: {target.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future, "\
                            f"it is recommended to use `{ctx.prefix}mute <user> [reason]`"\
                            f" as the reason is automatically sent to the user."

        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(chan_message)
            except:
                pass  # w/e, dumbasses forgot to set send perms properly.
        session = self.bot.db.dbsession()
        role_sticky = Restrictions(guild_id=ctx.guild.id, user_id=target.id, sticky_role=role.id)
        session.merge(role_sticky)
        session.commit()
        session.close()
        self.bot.log.info(f"{target} had a restriction applied!")
        await ctx.send(f"{target.mention} can no longer speak.")

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(manage_roles=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def unmute(self, ctx, target: discord.Member):
        """Unmutes a user, Moderator+ only"""
        session = self.bot.db.dbsession() # Check to see if mute role is setup
        try:
            role_id = session.query(Config).filter_by(guild_id=ctx.guild.id).one()
            role = discord.Object(id=role_id.mute_role_id)
        except:
            role_id = None
            return await ctx.send("❌ You don't have a mute role setup.")
        

        await target.remove_roles(role, reason=str(ctx.author))
        safe_name = await commands.clean_content().convert(ctx, str(target))

        chan_message = f"🔈 **Unmuted**: {ctx.author.mention} unmuted "\
                       f"{target.mention} | {safe_name}\n"\
                       f"🏷 __User ID__: {target.id}\n"

        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(chan_message)
            except:
                pass  # w/e, dumbasses forgot to set send perms properly.
        session = self.bot.db.dbsession()
        role_no = session.query(Restrictions).filter_by(guild_id=ctx.guild.id, user_id=target.id, sticky_role=role.id).delete()
        if role_no is None:
            self.bot.log.info(f"{target} did not have a restriction applied.")
        session.commit()
        session.close()
        self.bot.log.info(f"Restriction removed from {target}") # Make sure everything's working
        await ctx.send(f"{target.mention} can now speak again.")

    @commands.guild_only()
    @commands.command()
    @commands.bot_has_permissions(ban_members=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def unban(self, ctx, user_id: int, *, reason: str = ""):
        """Unbans a user, Moderator+ only"""
        member = discord.Object(id=user_id)
        try:
            await ctx.guild.unban(member, reason=str(ctx.author))
        except discord.HTTPException:
            return await ctx.send(f"❌ Unable to unban user with ID `{user_id}`")

        chan_message = f"⭕ **Unban**: {ctx.author.mention} unbanned "\
                       f"<@{user_id}>\n"\
                       f"🏷 __User ID__: {member.id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future, "\
                            f"it is recommended to use `{ctx.prefix}unban <user_id> [reason]`."
        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(chan_message)
            except:
                pass  # w/e, dumbasses forgot to set send perms properly.
        await ctx.send(f"{user_id} is now unbanned.")

    @commands.guild_only()
    @commands.command(aliases=['hackban'])
    @commands.bot_has_permissions(ban_members=True)
    @db.mod_check.check_if_at_least_has_staff_role("Moderator")
    async def banid(self, ctx, user_id: int, *, reason: str = ""):
        """Bans a user by ID (hackban), Moderator+"""
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
        elif target_member and db.mod_check.member_at_least_has_staff_role(target_member):
            return await ctx.send("I can't ban this user as "
                                  "they're a staff member.")
        userlog(ctx.guild, user_id, ctx.author, reason, "bans", user.name)

        safe_name = await commands.clean_content().convert(ctx, str(user_id))

        await ctx.guild.ban(user,
                            reason=f"{ctx.author}, reason: {reason}",
                            delete_message_days=0)
        chan_message = f"⛔ **Hackban**: {ctx.author.mention} banned "\
                       f"{user.mention} | {safe_name}\n"\
                       f"🏷 __User ID__: {user_id}\n"
        if reason:
            chan_message += f"✏️ __Reason__: \"{reason}\""
        else:
            chan_message += f"\nPlease add an explanation below. In the future"\
                            f", it is recommended to use "\
                            f"`{ctx.prefix}banid <user> [reason]`."
        if "log_channel" in ctx.guild_config:
            log_channel = self.bot.get_channel(ctx.guild_config["log_channel"])
            try:
                await log_channel.send(chan_message)
            except:
                pass  # w/e, dumbasses forgot to set send perms properly.
        await ctx.send(f"{safe_name} is now b&. 👍")




   # @Cog.listener()
   # async def on_member_join(self, member):
   #     session = self.bot.db.dbsession()
   #     server_id = member.guild.id
   #     check = session.query(Restrictions).filter_by(guild_id=member.guild.id, user_id=member.id, sticky_role=role.id).all()
   #     if member.id in check:
   #         await member.add_roles(role_id, reason="Reapply Restriction Role")
   #     else:
   #         session.close()
   #         return






def setup(bot):
    bot.add_cog(Moderation(bot))
