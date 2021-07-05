"""
Lightning.py - A Discord bot
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
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union

import discord

from lightning.formatters import truncate_text
from lightning.utils.helpers import Emoji
from lightning.utils.time import get_utc_timestamp, natural_timedelta


class ActionType(discord.Enum):
    WARN = 1
    KICK = 2
    BAN = 3
    TIMEBAN = 4
    UNBAN = 5
    MUTE = 6
    UNMUTE = 7
    TIMEMUTE = 8
    TEMPROLE = 9

    def __str__(self):
        return self.name

    def upper(self):
        return self.name.replace(" ", "_").upper()


class BaseFormat:
    def __init__(self, log_action, target, moderator, infraction_id, reason=None, *, expiry=None, **kwargs):
        self.log_action = log_action
        self.target = target
        self.moderator = moderator
        self.infraction_id = infraction_id
        self.reason = reason or "no reason given"
        self.timestamp = kwargs.pop("timestamp", datetime.utcnow())
        self.expiry = expiry
        self.kwargs = kwargs

    @classmethod
    def from_action(cls, action):
        if not action.is_logged():
            raise  # TODO

        return cls(action.action, action.target, action.moderator, action.infraction_id, action.reason,
                   timestamp=action.timestamp, expiry=action.expiry, **action.kwargs)

    def format_message(self):
        raise NotImplementedError


@dataclass
class CompactModAction:
    tense: str
    emoji: str
    title: str
    color: Union[discord.Color, int, hex]


log_actions = {
    "ban": CompactModAction("banned", "\N{NO ENTRY}", "Ban", 0xFF0000),
    "kick": CompactModAction("kicked", "\N{WOMANS BOOTS}", "Kick", 0xFF7F50),
    "warn": CompactModAction("warned", "\N{WARNING SIGN}", "Warn", 0xFFDF00),
    "temprole": CompactModAction("temporarily restricted role to", "\N{TIMER CLOCK}\N{VARIATION SELECTOR-16}",
                                 "Temporary Role", 0x607d8b),
    "unban": CompactModAction("unbanned", "\N{WARNING SIGN}", "Unban", 0xB22222),
    "timed_restriction_removed": CompactModAction("", "\N{WARNING SIGN}", "Timed restriction expired", 0x6B8E23),
    "timeban": CompactModAction("temporarily banned", "\N{NO ENTRY}", "Timed Ban", 0xC7031E),
    "mute": CompactModAction("muted", "\N{SPEAKER WITH CANCELLATION STROKE}", "Mute", 0x7c7b82),
    "timemute": CompactModAction("temporarily muted", "\N{SPEAKER WITH CANCELLATION STROKE}", "Timed Mute", 0x7c7b82),
    "unmute": CompactModAction("umuted", "\N{SPEAKER}", "Unmute", 0xFFFFFF)
}


def construct_dm_message(member, action, location, *, middle=None, reason=None, ending=None):
    msg = [f"You were {action} {location} {member.guild.name}"]
    if middle:
        msg.append(middle)
    if reason:
        msg.append(f"\n\nThe given reason is {reason}")
    if ending:
        msg.append(ending)
    return ''.join(msg)


class EmojiFormat(BaseFormat):
    def target_mention_and_safe_name(self):
        if self.target is None:
            return ""
        if hasattr(self.target, 'mention'):
            mention = self.target.mention
        else:
            mention = f"<@!{self.target.id}>"
        if isinstance(self.target, discord.Object):
            return mention
        return f"{mention} | {discord.utils.escape_markdown(str(self.target))}"

    def temp_action_target(self, expiry):
        if hasattr(self.target, 'mention'):
            mention = self.target.mention
        else:
            mention = f"<@!{self.target.id}>"
        if isinstance(self.target, discord.Object):
            return mention
        return f"{mention} for {expiry} | {discord.utils.escape_markdown(str(self.target))}"

    def format_message(self) -> str:
        attrs = log_actions[str(self.log_action).lower()]
        message = [f"{attrs.emoji} **{attrs.title}**: {self.moderator.mention}"
                   f" {attrs.tense} "]

        if self.expiry:
            message.append(self.temp_action_target(self.expiry))
        else:
            message.append(self.target_mention_and_safe_name())

        if hasattr(self.target, 'id'):
            message.append(f"\n\N{LABEL} __User ID__: {self.target.id}")

        message.append(f"\n\N{PENCIL}\N{VARIATION SELECTOR-16} __Reason__: \"{self.reason}\"")
        return ''.join(message)

    @staticmethod
    def bot_addition(bot: discord.Member, mod) -> str:
        return f"\N{ROBOT FACE} **Bot Add** {mod.mention} added bot {bot.mention} | "\
               f"{escape_markdown_and_mentions(str(bot))}"

    @staticmethod
    def role_change(added, removed, after, *, entry=None):
        mod = None
        if entry:
            mod = entry.user
            removed = entry.changes.before.roles
            added = entry.changes.after.roles

        msg = ["\n👑__Role change__: "]
        if len(added) != 0 or len(removed) != 0:
            roles = []
            for role in removed:
                safe_role_name = escape_markdown_and_mentions(role.name)
                roles.append("_~~" + safe_role_name + "~~_")

            for role in added:
                safe_role_name = escape_markdown_and_mentions(role.name)
                roles.append("__**" + safe_role_name + "**__")

            for role in after.roles:
                if role.name == "@everyone":
                    continue

                if role not in added and role not in removed:
                    roles.append(escape_markdown_and_mentions(role.name))

        msg.append(", ".join(roles))
        safe_user = escape_markdown_and_mentions(str(after))
        msg = [f"\N{INFORMATION SOURCE} **Member update**: {safe_user} | "
               f"{after.id} {''.join(msg)}"]
        if mod:
            safe_mod = escape_markdown_and_mentions(str(mod))
            msg.append(f"\n\N{BLUE BOOK} __Moderator__: "
                       f"{safe_mod} ({mod.id})")
        return ''.join(msg)

    @staticmethod
    def timed_action_expired(action, user, mod, creation) -> str:
        msg = [f"\N{WARNING SIGN} **{action.capitalize()} expired**: <@!{user.id}>"]

        if hasattr(user, 'name'):
            msg.append(f" | {discord.utils.escape_mentions(str(user))}")

        msg.append(f"\nTime{action} was made by <@!{mod.id}>")

        if hasattr(mod, 'name'):
            msg.append(f" | {discord.utils.escape_mentions(str(mod))}")

        msg.append(f" at {get_utc_timestamp(creation)}")
        return ''.join(msg)

    @staticmethod
    def join_leave(log_type: str, member) -> str:
        safe_name = escape_markdown_and_mentions(str(member))
        if log_type == "MEMBER_JOIN":
            msg = f"{Emoji.member_join}"\
                  f" **Member Join**: {member.mention} | "\
                  f"{safe_name}\n"\
                  f"\N{CLOCK FACE FOUR OCLOCK} __Account Creation__: {member.created_at}\n"\
                  f"\N{LABEL} __User ID__: {member.id}"
        else:
            msg = f"{Emoji.member_leave} "\
                  f"**Member Leave**: {member.mention} | "\
                  f"{safe_name}\n"\
                  f"\N{LABEL} __User ID__: {member.id}"
        return msg

    @staticmethod
    def command_ran(ctx) -> str:
        command = ctx.command
        msg = f"\N{CLIPBOARD} **Command Used**: {ctx.author.mention} ran `{command.qualified_name}`\n"\
              f"__Channel__: {ctx.channel.mention} | {ctx.channel.name}"
        return msg

    @staticmethod
    def nick_change(member, previous, current, moderator=None):
        if previous is None and current is not None:
            msg = f"\N{LABEL} __Nickname added__: None -> {current}"
        elif previous is not None and current is not None:
            msg = f"\N{LABEL} __Nickname changed__: {previous} -> {current}"
        elif previous is not None and current is None:
            msg = f"\N{LABEL} __Nickname removed__: {previous} -> None"

        msg = [f"\N{INFORMATION SOURCE} **Member update**: {member} | "
               f"{member.id} {msg}"]

        if moderator:
            safe_mod = escape_markdown_and_mentions(str(moderator))
            msg.append(f"\n\N{BLUE BOOK} __Moderator__: "
                       f"{safe_mod} ({moderator.id})")

        return ''.join(msg)


def escape_markdown_and_mentions(text) -> str:
    """Helper function to escape mentions and markdown from a string

    Parameters
    ----------
    text : str
        The string to remove markdown and mentions from

    Returns
    -------
    str
        The escaped text
    """
    escaped_markdown = discord.utils.escape_markdown(text)
    return discord.utils.escape_mentions(escaped_markdown)


def action_format(author, action_text="Action done by", *, reason=None) -> str:
    if reason is None:
        return f"{action_text} {str(author)} (ID: {author.id})"
    else:
        return f"{str(author)} (ID: {author.id}): {reason}"


def base_user_format(user, unknown_text="Unknown user with ID: ") -> str:
    if hasattr(user, 'name'):
        return f"{escape_markdown_and_mentions(str(user))} ({user.id})"
    else:
        return f"{unknown_text}{user.id if hasattr(user, 'id') else user}"


class MinimalisticFormat(BaseFormat):
    @staticmethod
    def format_user(user) -> str:
        if hasattr(user, 'name'):
            return f"{escape_markdown_and_mentions(str(user))} ({user.id})"
        else:
            return f"ID: {user.id}"

    @staticmethod
    def role_change(user, added, removed, *, entry=None, with_timestamp=True) -> str:
        time = datetime.utcnow()
        mod = None
        reason = None

        if entry:
            mod = entry.user
            time = entry.created_at
            removed = entry.changes.before.roles
            added = entry.changes.after.roles
            reason = entry.reason

        if with_timestamp:
            base = [f"`[{time.strftime('%H:%M:%S UTC')}]` **Role Change**\n"
                    f"**User**: {escape_markdown_and_mentions(str(user))} ({user.id})\n"]
        else:
            base = ["**Role Change**\n**User**:"
                    f"{escape_markdown_and_mentions(str(user))} ({user.id})\n"]

        if added != 0:
            for role in added:
                base.append(f"**Role Added**: {escape_markdown_and_mentions(str(role))} ({role.id})\n")
        if removed != 0:
            for role in removed:
                base.append(f"**Role Removed**: {escape_markdown_and_mentions(str(role))} ({role.id})\n")

        if mod is not None:
            base.append(f"**Moderator**: {escape_markdown_and_mentions(str(mod))} ({mod.id})")

        if reason:
            base.append(f"\n**Reason**: {escape_markdown_and_mentions(reason)}")

        return ''.join(base)

    @staticmethod
    def timed_action_expired(action, user, mod, creation, expiry, *, with_timestamp: bool = True) -> str:
        text = [f"`[{expiry.strftime('%H:%M:%S UTC')}]` "] if with_timestamp else []

        text.append(f"**{action.capitalize()} expired**\n**User**: "
                    f"{MinimalisticFormat.format_user(user)}\n**Moderator**: {MinimalisticFormat.format_user(mod)}"
                    f"\n**Created at**: {get_utc_timestamp(creation)}")
        return ''.join(text)

    @staticmethod
    def bot_addition(bot, mod, time) -> str:
        safe_name = escape_markdown_and_mentions(str(bot))
        safe_mod_name = escape_markdown_and_mentions(str(mod))
        return f"`[{time.strftime('%H:%M:%S UTC')}]` **Bot Add**"\
               f"\n**Bot**: {safe_name} ({bot.id})\n"\
               f"**Moderator**: {safe_mod_name} ({mod.id})"

    @staticmethod
    def join_leave(log_type: str, member) -> str:
        if log_type == "MEMBER_JOIN":
            msg = f"`[{member.joined_at.strftime('%H:%M:%S UTC')}]`"\
                  f" **Member Join**: {discord.utils.escape_markdown(str(member))} ({member.id})\n"\
                  "__Account Creation Date__: "\
                  f"{get_utc_timestamp(member.created_at)}"
        else:
            msg = f"`[{datetime.utcnow().strftime('%H:%M:%S UTC')}]`"\
                  f" **Member Leave**: {discord.utils.escape_markdown(str(member))} ({member.id})"
        return msg

    @staticmethod
    def command_ran(ctx, *, with_timestamp: bool = True) -> str:
        timestamp = ctx.message.created_at

        if with_timestamp:
            base = [f"`[{timestamp.strftime('%H:%M:%S UTC')}]` "]
        else:
            base = []

        base.append(f"**Command Ran**\n**Command**: {ctx.command.qualified_name}\n**User**: "
                    f"{MinimalisticFormat.format_user(ctx.author)}\n"
                    f"**Channel**: {base_user_format(ctx.channel)}")

        return ''.join(base)

    @staticmethod
    def nick_change(member, previous: str, current: Optional[str], moderator=None, *, with_timestamp: bool = True):
        timestamp = datetime.utcnow()

        if with_timestamp:
            base = [f"`[{timestamp.strftime('%H:%M:%S UTC')}]`"]
        else:
            base = []

        if current and previous:
            base.append(f"**Member Nickname Update**\n**Old Nickname**: {previous}\n**New Nickname**: {current}")
        elif previous is None and current is not None:
            base.append(f"**Member Nickname Add**\n**New Nickname**: {current}")
        elif current is None and previous is not None:
            base.append(f"**Member Nickname Removed**\n**Old Nickname**: {previous}")

        base.append(f"**Member**: {MinimalisticFormat.format_user(member)}")

        if moderator:
            base.append(f"\n**Moderator**: {MinimalisticFormat.format_user(moderator)}")

        return ''.join(base)

    def format_message(self, *, with_timestamp: bool = True) -> str:
        """Formats a log entry."""
        entry_time = self.timestamp
        log_action = log_actions[str(self.log_action).lower()]

        if with_timestamp:
            base = [f"`[{entry_time.strftime('%H:%M:%S UTC')}]` "]
        else:
            base = []

        base.append(f"**{log_action.title}** | Infraction ID {self.infraction_id}"
                    f"\n**User**: {self.format_user(self.target)}\n**Moderator**: {self.format_user(self.moderator)}")

        if self.expiry:
            base.append(f"\n**Expiry**: {self.expiry}")

        base.append(f"\n**Reason**: {escape_markdown_and_mentions(self.reason)}")
        return ''.join(base)


class EmbedFormat(BaseFormat):
    @staticmethod
    def join_leave(log_type: str, member):
        embed = discord.Embed()

        if log_type == "MEMBER_JOIN":
            embed.title = "Member Join"
            embed.color = discord.Color.green()
        else:
            embed.title = "Member Leave"
            embed.color = discord.Color.red()

        embed.set_author(name=member, icon_url=member.avatar_url)
        embed.description = f"**User**: {member.mention} ({member.id}) \n**Created at**: "\
                            f"{natural_timedelta(member.created_at)}"
        return embed

    def format_message(self) -> discord.Embed:
        action = log_actions[str(self.log_action).lower()]
        embed = discord.Embed(title=action.title, color=action.color)
        reason = truncate_text(self.reason, 512)

        base = [f"**User**: {str(self.target)} <@!{self.target.id}>\n"
                f"**Moderator**: {str(self.moderator)} <@!{self.moderator.id}>"]

        if self.expiry:
            base.append(f"\n**Expiry**: {self.expiry}")

        base.append(f"\n**Reason**: {discord.utils.escape_markdown(reason)}")
        embed.description = ''.join(base)
        embed.set_footer(text=f"Infraction ID: {self.infraction_id}")
        embed.timestamp = self.timestamp
        return embed

    @staticmethod
    def timed_action_expired(action, moderator, user, created_at) -> discord.Embed:
        embed = discord.Embed(description=f"Time {action} for {base_user_format(user)} expired")
        embed.add_field(name="Moderator", value=base_user_format(moderator))
        embed.timestamp = created_at
        embed.set_footer(text=f"Time {action} was made at")
        return embed

    @staticmethod
    def role_change(user, added, removed, *, entry=None):
        embed = discord.Embed(title="Role Change", color=discord.Color.dark_gold(),
                              description=f"User: {user.mention} ({user.id})")

        time = datetime.utcnow()
        if entry:
            removed = entry.changes.before.roles
            added = entry.changes.after.roles
            time = entry.created_at

            embed.add_field(name="Moderator", value=base_user_format(entry.user))

        if added:
            added = "".join(r.mention for r in added)
            embed.description += f"\nAdded: {added}"

        if removed:
            removed = "".join(r.mention for r in removed)
            embed.description += f"\nRemoved: {removed}"

        embed.timestamp = time
        return embed

    @staticmethod
    def command_ran(ctx) -> discord.Embed:
        embed = discord.Embed(title="Command Ran", color=0xf74b06, timestamp=ctx.message.created_at)
        user = ctx.author
        embed.description = f"**Command**: {ctx.command.qualified_name}\n**User**: {user.mention} ({user.id})"\
                            f"**Channel**: {ctx.channel.mention} ({ctx.channel.id})"
        return embed

    @staticmethod
    def nick_change(member, previous: str, current: Optional[str], moderator=None) -> discord.Embed:
        embed = discord.Embed(color=discord.Color.blurple(), timestamp=datetime.utcnow())

        if current and previous:
            embed.title = "Member Nickname Update"
            embed.description = f"**Old Nickname**: {previous}\n**New Nickname**: {current}"
        elif previous is None and current is not None:
            embed.title = "Member Nickname Add"
            embed.description = f"**New Nickname**: {current}"
        elif current is None and previous is not None:
            embed.title = "Member Nickname Removed"
            embed.description = f"**Old Nickname**: {previous}"

        if moderator:
            embed.add_field(name="Moderator", value=base_user_format(moderator))

        return embed
