# Lightning.py - A multi-purpose Discord bot
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

from datetime import datetime

import discord
from bolt.time import get_utc_timestamp

from resources import botemojis


class Action:
    def __init__(self, target, mod, *, reason=None, **kwargs):
        self.target = target
        self.mod = mod
        self.kwargs = kwargs
        self.reason = reason


# TODO: Clean this function
def kurisu_format(log_action: str, target, moderator, reason: str = "", **kwargs):
    """Formats a log entry, NH Kurisu style.

    Parameters:
    -----------
    log_action: `str`
        The type of mod action that was done.
    target:
        The member that got the log_action taken.
    moderator:
        The responsible moderator who did the action.
    reason: `str`
        The reason why the action was taken.
    """
    safe_name = discord.utils.escape_mentions(str(target))
    if log_action.lower() == "kick":
        message = f"\N{WOMANS BOOTS} **Kick**: {moderator.mention} kicked "\
                  f"{target.mention} | {safe_name}\n"\
                  f"🏷 __User ID__: {target.id}\n"
        if reason:
            message += f"\N{PENCIL} __Reason__: \"{reason}\""
        else:
            message += "\nPlease add an explanation below."
        return message
    elif log_action.lower() == "ban":
        message = f"\N{NO ENTRY} **Ban**: {moderator.mention} banned "\
                  f"{target.mention} | {safe_name}\n"\
                  f"\N{LABEL} __User ID__: {target.id}\n"
        if reason:
            message += f"\N{PENCIL} __Reason__: \"{reason}\""
        else:
            message += "\nPlease add an explanation below."
        return message
    elif log_action.lower() == "mute":
        message = f"\N{SPEAKER WITH CANCELLATION STROKE} **Mute**: "\
                  f"{moderator.mention} muted {target.mention}"\
                  f" | {safe_name}\n"\
                  f"\N{LABEL} __User ID__: {target.id}\n"
        if reason:
            message += f"\N{PENCIL} __Reason__: \"{reason}\""
        else:
            message += "\nPlease add an explanation below."
        return message
    elif log_action.lower() == "timemute":
        expiry = kwargs.pop('expiry')
        message = f"\N{SPEAKER WITH CANCELLATION STROKE} **Time Mute**: "\
                  f"{moderator.mention} temporarily muted {target.mention}"\
                  f" for {expiry} | {safe_name}\n"\
                  f"\N{LABEL} __User ID__: {target.id}\n"
        if reason:
            message += f"\N{PENCIL} __Reason__: \"{reason}\""
        else:
            message += "\nPlease add an explanation below."
        return message
    elif log_action.lower() == "timeban":
        expiry = kwargs.pop('expiry')
        message = f"\N{NO ENTRY} **Timed Ban**: {moderator.mention} banned "\
                  f"{target.mention} for {expiry} | {safe_name}\n"\
                  f"\N{LABEL} __User ID__: {target.id}\n"
        if reason:
            message += f"\N{PENCIL} __Reason__: \"{reason}\""
        else:
            message += "\nPlease add an explanation below."
        return message
    elif log_action.lower() == "warn":
        warn_count = kwargs.pop('warn_count')
        message = f"\N{WARNING SIGN} **Warned**: "\
                  f"{moderator.mention} warned {target.mention}" \
                  f" (warn #{warn_count}) | {safe_name}\n"
        if reason:
            message += f"\N{PENCIL} __Reason__: \"{reason}\""
        else:
            message += "\nPlease add an explanation below."
        return message
    elif log_action.lower() == "lockdown":
        channel = kwargs.pop('lockdown_channel')
        safe_name = discord.utils.escape_mentions(str(moderator))
        message = f"\N{LOCK} **Lockdown** in {channel.mention} "\
                  f"by {moderator.mention} | {safe_name}"
        return message
    elif log_action.lower() == "hard-lockdown":
        channel = kwargs.pop('lockdown_channel')
        safe_name = discord.utils.escape_mentions(str(moderator))
        message = f"\N{LOCK} **Hard Lockdown** in {channel.mention} "\
                  f"by {moderator.mention} | {safe_name}"
        return message
    elif log_action.lower() == "unlock":
        channel = kwargs.pop('lockdown_channel')
        safe_name = discord.utils.escape_mentions(str(moderator))
        message = f"\N{OPEN LOCK} **Unlock** in {channel.mention} "\
                  f"by {moderator.mention} | {safe_name}"
        return message
    elif log_action.lower() == "unmute":
        message = "\N{SPEAKER} **Unmuted**: "\
                  f"{moderator.mention} unmuted {target.mention}"\
                  f" | {safe_name}\n"\
                  f"\N{LABEL} __User ID__: {target.id}\n"
        if reason:
            message += f"\N{PENCIL} __Reason__: \"{reason}\""
        else:
            message += "\nPlease add an explanation below."
        return message
    elif log_action.lower() == "clearwarns":
        message = "\N{WASTEBASKET} **Cleared warns**: "\
                  f"{moderator.mention} cleared all warns of "
        if hasattr(target, 'id'):
            message += f"{target.mention} | {safe_name}"
        else:
            message += f"<@!{target}>"
        return message
    elif log_action.lower() == "clearwarn":
        idx = kwargs.pop('warn_number')
        message = "\N{WASTEBASKET} **Deleted warn**: "\
                  f"{moderator.mention} removed warn {idx}"
        if hasattr(target, 'id'):
            message += f" from {target.mention} | {safe_name}"
        else:
            message += f" from <@!{target}>"
        return message
    elif log_action.lower() == "timed_restriction_removed":
        role = kwargs.pop('role')
        job_created = kwargs.pop('job_creation')
        if hasattr(target, 'id'):
            message = f"\N{WARNING SIGN} **Timed restriction expired:** <@!{target.id}> "\
                      f"| {target.id}\n"
        else:
            message = f"\N{WARNING SIGN}  **Timed restriction expired** <@!{target}>\n"
        message += f"\N{LABEL} __Role__: {discord.utils.escape_mentions(role.name)} "\
                   f"| {role.id}\n"\
                   f"Timed restriction was made by "\
                   f"{discord.utils.escape_mentions(str(moderator))} at "\
                   f"{get_utc_timestamp(job_created)}."
        return message
    elif log_action.lower() == "unban":
        message = f"\N{WARNING SIGN} **Unban**: {moderator.mention} "\
                  f"unbanned {target.mention} | {safe_name}\n"\
                  f"\N{LABEL} __User ID__: {target.id}\n"
        if reason:
            message += f"\N{PENCIL} __Reason__: \"{reason}\""
        else:
            message += "\nPlease add an explanation below."
        return message
    elif log_action.lower() == "purge":
        message_count = kwargs.pop('messages')
        message = f"\N{WASTEBASKET} **{message_count} messages purged** in "\
                  f"{safe_name} | {target.mention}\n"\
                  f"Purger was {moderator.mention} | "\
                  f"{discord.utils.escape_mentions(str(moderator))}"
        if reason:
            message += f"\n\N{PENCIL} __Reason__: {reason}"
        return message
    else:
        return None


def kurisu_join_leave(log_type: str, member) -> str:
    safe_name = discord.utils.escape_mentions(str(member))
    if log_type.lower() == "join":
        msg = f"{botemojis.member_join}"\
              f" **Member Join**: {member.mention} | "\
              f"{safe_name}\n"\
              f"\N{CLOCK FACE FOUR OCLOCK} __Account Creation__: {member.created_at}\n"\
              f"\N{SPIRAL CALENDAR PAD} Join Date: {member.joined_at}\n"\
              f"\N{LABEL} __User ID__: {member.id}"
    elif log_type.lower() == "leave":
        msg = f"{botemojis.member_leave} "\
              f"**Member Leave**: {member.mention} | "\
              f"{safe_name}\n"\
              f"\N{LABEL} __User ID__: {member.id}"
    return msg


def lightning_join_leave(log_type: str, member) -> str:
    safe_name = discord.utils.escape_mentions(str(member))
    if log_type.lower() == "join":
        msg = f"`[{member.joined_at.strftime('%H:%M:%S UTC')}]`"\
              f" **Member Join**: {safe_name} ({member.id})\n"\
              "__Account Creation Date__: "\
              f"{get_utc_timestamp(member.created_at)}"
    elif log_type.lower() == "leave":
        msg = f"`[{datetime.utcnow().strftime('%H:%M:%S UTC')}]`"\
              f" **Member Leave**: {safe_name} ({member.id})"
    return msg


def kurisu_bot_add(bot, mod) -> str:
    safe_name = discord.utils.escape_mentions(str(bot))
    return f"\N{ROBOT FACE} **Bot Add** {mod.mention} added bot {bot.mention} | {safe_name}"


def lightning_bot_add(bot, mod, time) -> str:
    safe_name = discord.utils.escape_mentions(str(bot))
    safe_mod_name = discord.utils.escape_mentions(str(mod))
    return f"`[{time.strftime('%H:%M:%S UTC')}]` **Bot Add**"\
           f"\n**Bot**: {safe_name} ({bot.id})\n"\
           f"**Moderator**: {safe_mod_name} ({mod.id})"


def kurisu_time_ban_expired(user, mod, creation):
    if isinstance(user, discord.User):
        msg = f"\N{WARNING SIGN} **Ban expired**: <@!{user.id}> "\
              f"| {discord.utils.escape_mentions(str(user))}"
    elif isinstance(user, discord.Object):
        msg = f"\N{WARNING SIGN} **Ban expired**: <@!{user.id}> "
    msg += "\nTimeban was made by "
    if isinstance(mod, (discord.Member, discord.User)):
        msg += f"<@!{mod.id}> | {discord.utils.escape_mentions(str(mod))}"
    elif isinstance(mod, discord.Object):
        msg += f"<@!{mod.id}>"
    msg += f" at {get_utc_timestamp(creation)}"
    return msg


def lightning_time_ban_expired(user, mod, creation, expiry):
    msg = f"`[{expiry.strftime('%H:%M:%S UTC')}]` "
    if isinstance(user, discord.User):
        msg += f"**Ban expired**\n**User**: {discord.utils.escape_mentions(str(user))} ({user.id})"
    elif isinstance(user, discord.Object):
        msg += f"**Ban expired**\n**User**: {user.id}"
    msg += "\n**Moderator**: "
    if isinstance(mod, (discord.Member, discord.User)):
        msg += f"{discord.utils.escape_mentions(str(mod))} ({mod.id})"
    elif isinstance(mod, discord.Object):
        msg += f"{mod.id}"
    msg += f"\n**Created at**: {get_utc_timestamp(creation)}"
    return msg


def kurisu_role_change(added, removed, after, mod):
    msg = ""
    if len(added) != 0 or len(removed) != 0:
        msg += "\n👑 __Role change__: "
        roles = []
        for role in removed:
            roles.append("_~~" + role.name + "~~_")
        for role in added:
            roles.append("__**" + role.name + "**__")
        for index, role in enumerate(after.roles):
            if role.name == "@everyone":
                continue
            if role not in added and role not in removed:
                roles.append(role.name)
    msg += ", ".join(roles)
    if msg:  # Ending
        msg = f"\N{INFORMATION SOURCE} "\
              f"**Member update**: {discord.utils.escape_mentions(str(after))} | "\
              f"{after.id} {msg}\n\N{BLUE BOOK} __Moderator__: "\
              f"{discord.utils.escape_mentions(str(mod))} ({mod.id})"
        return msg


def lightning_role_change(user, added, removed, mod, time, reason: str = ""):
    base = f"`[{time.strftime('%H:%M:%S UTC')}]` **Role Change**\n"\
           f"**User**: {discord.utils.escape_mentions(str(user))} ({user.id})\n"
    if added != 0:
        for role in added:
            base += f"**Role Added**: {discord.utils.escape_mentions(str(role))} ({role.id})\n"
    if removed != 0:
        for role in removed:
            base += f"**Role Removed**: {discord.utils.escape_mentions(str(role))} ({role.id})\n"
    base += f"**Moderator**: {discord.utils.escape_mentions(str(mod))} ({mod.id})"
    if reason:
        base += f"\n**Reason**: {discord.utils.escape_mentions(reason)}"
    return base


def kurisu_temprole(target, mod, role, expiry, reason):
    base = f"\N{OCTAGONAL SIGN} **Timed Role Restriction**: {mod.mention} role restricted"\
           f" {target.mention} with role {role.name} ({role.id}) which expires in {expiry}\n"
    if reason:
        base += f"\N{PENCIL} __Reason__: \"{reason}\""
    else:
        base += "\nPlease add an explanation below."
    return base


log_action_meanings = {"unban": "Unban",
                       "timed_restriction_removed": "Timed restriction expired",
                       "ban": "Ban",
                       "clearwarn": "Deleted Warn",
                       "clearwarns": "Cleared Warns",
                       "mute": "Mute",
                       "unmute": "Unmute",
                       "timemute": "Timed Mute",
                       "timeban": "Timed Ban",
                       "purge": "Purge",
                       "warn": "Warn",
                       "lockdown": "Lockdown",
                       "unlock": "Unlock",
                       "hard-lockdown": "Hard Lockdown",
                       "temprole": "Timed Role Restriction",
                       "kick": "Kick"}


def lightning_format(log_action: str, target, moderator, reason: str = "", time=None, **kwargs):
    """Formats a log entry. Lightning styled."""
    entry_time = time
    safe_name = discord.utils.escape_mentions(str(target))
    safe_mod_name = discord.utils.escape_mentions(str(moderator))
    log_action = log_action.lower()
    if not entry_time:
        entry_time = datetime.utcnow()
    base = f"`[{entry_time.strftime('%H:%M:%S UTC')}]` **{log_action_meanings[log_action]}**"
    if log_action == "purge":
        message_count = kwargs.pop('messages')
        if hasattr(moderator, 'id'):
            base += f"\n**Moderator**: {safe_mod_name} ({moderator.id})"
        else:
            base += f"\n**Moderator**: {safe_mod_name}"
        base += f"\n**Channel**: #{safe_name} ({target.id})\n"\
                f"**Messages Purged**: {message_count}"
        if reason:
            base += f"\n**Reason**: {discord.utils.escape_mentions(reason)}"
        else:
            base += f"\n**Reason**: no reason given"
        return base
    if log_action == ("lockdown" or "unlock" or "hard-lockdown"):
        if hasattr(moderator, 'id'):
            base += f"\n**Moderator**: {safe_mod_name} ({moderator.id})"
        else:
            base += f"\n**Moderator**: {safe_mod_name}"
        base += f"\n**Channel**: #{safe_name} ({target.id})\n"
        return base
    if log_action == "warn":
        warn_count = kwargs.pop('warn_count')
        base += f" (warn #{warn_count})"
    if log_action == "timed_restriction_removed":
        role = kwargs.pop('role')
        base += f"\n**Role**: {discord.utils.escape_mentions(str(role))} ({role.id})"
    if hasattr(target, 'id'):
        base += f"\n**User**: {safe_name} ({target.id})"
    else:
        base += f"\n**User**: {safe_name}"
    if hasattr(moderator, 'id'):
        base += f"\n**Moderator**: {safe_mod_name} ({moderator.id})"
    else:
        base += f"\n**Moderator**: {safe_mod_name}"
    if log_action == ("timemute" or "timeban" or "temprole"):
        expiry = kwargs.pop('expiry')
        base += f"\n**Expiry**: {expiry}"
    if reason:
        base += f"\n**Reason**: {discord.utils.escape_mentions(reason)}"
    else:
        base += f"\n**Reason**: no reason given"
    return base
