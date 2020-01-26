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

from datetime import datetime

import discord
from bolt.time import get_utc_timestamp

from resources import botemojis
from utils.time import plural


class KurisuFormat:
    __slots__ = ("log_action", "target", "moderator", "reason")

    def __init__(self, log_action, target, moderator, reason=None):
        self.log_action = log_action
        self.target = target
        self.moderator = moderator
        self.reason = discord.utils.escape_mentions(str(reason))

    def log_action_emoji(self):
        """Returns a log action emoji"""
        log_action = self.log_action.lower()
        aliases = {"hard-lockdown": "lockdown"}
        if log_action in aliases:
            log_action = aliases[log_action]
        emojis = {"kick": "\U0001f462", "ban": "\U000026d4", "warn": "\U000026a0",
                  "unban": "\U000026a0", "timed_restriction_removed": "\U000026a0",
                  "purge": "\U0001f5d1", "clearwarns": "\U0001f6ae",
                  "lockdown": "\U0001f512", "unlock": "\U0001f513", "mute": "\U0001f507",
                  "unmute": "\U0001f508", "pardonwarn": "\U0001f516",
                  "unpardonwarn": "\U000026a0", "timemute": "\U0001f507",
                  "timeban": "\U000026d4"}
        if log_action in emojis:
            return emojis[log_action]
        else:
            raise Exception("Invalid log action type!")

    def log_action_past_tense(self):
        """Returns past tense of a log action.

        Valid log actions are "kick", "ban", "warn", "unban",
        "purge", "clearwarns", "mute", "unmute", "timemute",
        "timeban", "pardonwarn", "unpardonwarn".
        """
        log_action = self.log_action.lower()
        pt = {"kick": "kicked", "ban": "banned", "warn": "warned",
              "unban": "unbanned", "purge": "purged",
              "clearwarns": "cleared all warns from", "mute": "muted",
              "unmute": "unmuted",
              "timemute": "temporarily muted", "timeban": "temporarily banned",
              "pardonwarn": "pardoned a warn from",
              "unpardonwarn": "unpardoned a warn from"}
        if log_action in pt:
            return pt[log_action]
        else:
            raise Exception("Invalid log action type!")

    def target_mention_and_safe_name(self):
        if self.target is None:
            return ""
        if hasattr(self.target, 'mention'):
            mention = self.target.mention
        else:
            mention = f"<@!{self.target.id}>"
        if isinstance(self.target, discord.Object):
            return f"{mention}"
        escape = discord.utils.escape_markdown(str(self.target))
        return f"{mention} | {discord.utils.escape_mentions(escape)}"

    def temp_action_target(self, expiry):
        if hasattr(self.target, 'mention'):
            mention = self.target.mention
        else:
            mention = f"<@!{self.target.id}>"
        if isinstance(self.target, discord.Object):
            return f"{mention}"
        return f"{mention} for {expiry} | {discord.utils.escape_mentions(str(self.target))}"

    # def lockdown(self, channel):

    def __repr__(self):
        return f"<KurisuFormat log_action={self.log_action} target={self.target} "\
               f"moderator={self.moderator} reason={self.reason}>"


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
    # Lazy things I don't want to fix yet
    if log_action.lower() == "timed_restriction_removed":
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
    if log_action.lower() in ("lockdown", "hard-lockdown", "unlock"):
        channel = kwargs.pop('lockdown_channel')
        safe_name = discord.utils.escape_mentions(str(moderator))
        kf = KurisuFormat(log_action, channel, moderator)
        message = f"{kf.log_action_emoji()} **{log_action.title()}**"\
                  f" in {channel.mention} "\
                  f"by {moderator.mention} | {safe_name}"
        return message
    if log_action.lower() == "purge":
        message_count = kwargs.pop('messages')
        message = f"\N{WASTEBASKET} **{plural(message_count):message} purged** in "\
                  f"{discord.utils.escape_mentions(str(target))} | {target.mention}\n"\
                  f"Purger was {moderator.mention} | "\
                  f"{discord.utils.escape_mentions(str(moderator))}"
        return message
    entry = KurisuFormat(log_action, target, moderator, reason)
    logemoji = entry.log_action_emoji()
    message = f"{logemoji} **{log_action_meanings[entry.log_action.lower()]}**: {entry.moderator.mention}"\
              f" {entry.log_action_past_tense()} "
    if log_action.lower() in ("timemute", "timeban", "temprole"):
        expiration = kwargs.pop('expiry')
        message += entry.temp_action_target(expiration)
    else:
        message += entry.target_mention_and_safe_name()
    if entry.log_action.lower() in ("warn", "pardonwarn", "unpardonwarn", "deletewarn"):
        warn = kwargs.pop('warn_id')
        message += f"\n\U0001f5c3 __Warn ID__: {warn}"
    if hasattr(target, 'id'):
        message += f"\n\U0001f3f7 __User ID__: {target.id}\n"
    if reason:
        message += f"\U0000270f __Reason__: \"{entry.reason}\""
    else:
        message += "\nPlease add an explanation below."
    return message


def kurisu_remove_warn_id(mod, warn_id: int, member=None):
    msg = f"\N{WASTEBASKET} **Deleted Warn** "\
          f"{mod.mention} deleted warn {warn_id}"
    # Future proofing
    if member:
        if isinstance(member, (discord.Object, discord.User)):
            msg += f" from {member.id}"
        else:
            msg += f" from {member.mention} | {discord.utils.escape_mentions(str(member))}"
    return msg


def lightning_remove_warn_id(mod, warn_id, time, member=None):
    msg = f"`[{time.strftime('%H:%M:%S UTC')}]` **Deleted Warn**"
    if member:
        if isinstance(member, (discord.Object)):
            msg += f"\n**User**: {member.id}"
        else:
            msg += f"\n**User**: {discord.utils.escape_mentions(str(member))}"\
                   f" ({member.id})"
    msg += f"\n**Moderator**: {discord.utils.escape_mentions(str(mod))}"\
           f" ({mod.id})\n**Warn ID**: {warn_id}"
    return msg


def kurisu_join_leave(log_type: str, member) -> str:
    safe_name = discord.utils.escape_mentions(str(member))
    if log_type.lower() == "join":
        msg = f"{botemojis.member_join}"\
              f" **Member Join**: {member.mention} | "\
              f"{safe_name}\n"\
              f"\N{CLOCK FACE FOUR OCLOCK} __Account Creation__: {member.created_at}\n"\
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


def kurisu_role_change(added, removed, after, mod=None):
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
        escape_md = discord.utils.escape_markdown(str(after))
        # Also escape markdown cause haha funny markdown characters in my name
        safe_user = discord.utils.escape_mentions(escape_md)
        msg = f"\N{INFORMATION SOURCE} "\
              f"**Member update**: {safe_user} | "\
              f"{after.id} {msg}"
        if mod:
            safe_md = discord.utils.escape_markdown(str(mod))
            safe_mod = discord.utils.escape_mentions(safe_md)
            msg += f"\n\N{BLUE BOOK} __Moderator__: "\
                   f"{safe_mod} ({mod.id})"
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
    if mod is not None:
        base += f"**Moderator**: {discord.utils.escape_mentions(str(mod))} ({mod.id})"
    else:
        pass
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
                       "kick": "Kick",
                       "pardonwarn": "Pardon Warn"}


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
        warn_count = kwargs.pop('warn_id')
        base += f" (Warn ID #{warn_count})"
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
