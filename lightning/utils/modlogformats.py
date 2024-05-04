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

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Union

import discord

from lightning.formatters import truncate_text
from lightning.models import Action
from lightning.utils.helpers import Emoji
from lightning.utils.time import get_utc_timestamp, natural_timedelta

if TYPE_CHECKING:
    from lightning.events import (AuditLogTimeoutEvent, InfractionDeleteEvent,
                                  InfractionUpdateEvent,
                                  MemberRolesUpdateEvent, MemberUpdateEvent)


class BaseFormat:
    def __init__(self, log_action, target, moderator, infraction_id, reason=None, *, expiry=None, **kwargs):
        self.log_action = log_action
        self.target = target
        self.moderator = moderator
        self.infraction_id = infraction_id
        self.reason = reason or "no reason given"
        self.timestamp = kwargs.pop("timestamp", discord.utils.utcnow())
        self.expiry: datetime | None = expiry
        self.kwargs = kwargs

    @classmethod
    def from_action(cls, action: Action):
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
    "unmute": CompactModAction("umuted", "\N{SPEAKER}", "Unmute", 0xFFFFFF),
    "timeout": CompactModAction("timed out", "\N{SPEAKER WITH CANCELLATION STROKE}", "Timeout", 0x7c7b82)
}


def construct_dm_message(member, action_verb, location, *, middle=None, reason=None, ending=None):
    msg = [f"You were {action_verb} {location} {member.guild.name}"]
    if middle:
        msg.append(middle)
    if reason:
        msg.append(f"\n\n**Reason**: {reason}")
    if ending:
        msg.append(f"\n{ending}")
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
    def completed_screening(member: discord.Member):
        return f"\N{PASSPORT CONTROL} **Member Completed Screening** {member.mention} | "\
               f"({escape_markdown_and_mentions(str(member))}"

    @staticmethod
    def role_change(event: MemberRolesUpdateEvent):
        if event.entry:
            removed = event.entry.changes.before.roles
            added = event.entry.changes.after.roles
        else:
            removed = event.removed_roles
            added = event.added_roles

        msg = ["\n👑__Role change__: "]
        if len(added) != 0 or len(removed) != 0:
            roles = []
            for role in removed:
                roles.append(f"_~~{escape_markdown_and_mentions(role.name)}~~_")

            for role in added:
                roles.append(f"__**{escape_markdown_and_mentions(role.name)}**__")

            for role in event.after.roles:
                if role.name == "@everyone":
                    continue

                if role not in added and role not in removed:
                    roles.append(escape_markdown_and_mentions(role.name))

        msg.append(", ".join(roles))
        msg = [f"\N{INFORMATION SOURCE} **Member update**: {escape_markdown_and_mentions(str(event.after))} | "
               f"{event.after.id} {''.join(msg)}"]

        if event.moderator:
            msg.append(f"\n\N{BLUE BOOK} __Moderator__: "
                       f"{escape_markdown_and_mentions(str(event.moderator))} ({event.moderator.id})")

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
                  f"\N{CLOCK FACE FOUR OCLOCK} __Account Creation__: {discord.utils.format_dt(member.created_at)}\n"\
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

    @staticmethod
    def infraction_update(event: InfractionUpdateEvent) -> str:
        base = [f"\N{MEMO} **Infraction update**: ID: {event.after.id}"]

        if event.before.moderator_id != event.after.moderator_id:
            base.append(f"\n__Old Moderator__: {escape_markdown_and_mentions(event.before.moderator)}"
                        f"\n__New Moderator__: {escape_markdown_and_mentions(event.after.moderator)}")

        if event.before.reason != event.after.reason:
            base.append(f"\n__Old Reason__: {truncate_text(event.before.reason, limit=200)}"
                        f"\n__New Reason__: {truncate_text(event.after.reason, limit=200)}")

        return ''.join(base)

    @staticmethod
    def timeout_expired(event: AuditLogTimeoutEvent | MemberUpdateEvent) -> str:
        text = [f"\N{WARNING SIGN} **Timeout expired** <@!{event.member.id}>"]

        if hasattr(event, 'moderator'):
            text.append(f"\N{BLUE BOOK} __Moderator__: "
                        f"{escape_markdown_and_mentions(str(event.moderator))} ({event.moderator.id})")

        return ''.join(text)

    @staticmethod
    def infraction_delete(event: InfractionDeleteEvent):
        msg = f"\N{PUT LITTER IN ITS PLACE SYMBOL} **Infraction deleted** "\
              f"{event.moderator.mention} deleted #{event.infraction.id}"
        return msg


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


def format_timestamp(dt: datetime):
    return discord.utils.format_dt(dt, style="T")


class MinimalisticFormat(BaseFormat):
    @staticmethod
    def format_user(user) -> str:
        if hasattr(user, 'name'):
            return f"{escape_markdown_and_mentions(str(user))} ({user.id})"
        else:
            return f"ID: {user.id}"

    @staticmethod
    def role_change(event: MemberRolesUpdateEvent, *, with_timestamp=True) -> str:
        time = event.entry.created_at if event.entry else discord.utils.utcnow()

        if with_timestamp:
            base = [f"[{format_timestamp(time)}] **Role Change**\n"
                    f"**User**: {escape_markdown_and_mentions(str(event.after))} ({event.after.id})\n"]
        else:
            base = ["**Role Change**\n**User**:"
                    f"{escape_markdown_and_mentions(str(event.after))} ({event.after.id})\n"]

        if event.added_roles != 0:
            for role in event.added_roles:
                base.append(f"**Role Added**: {escape_markdown_and_mentions(str(role))} ({role.id})\n")
        if event.removed_roles != 0:
            for role in event.removed_roles:
                base.append(f"**Role Removed**: {escape_markdown_and_mentions(str(role))} ({role.id})\n")

        if event.moderator is not None:
            base.append(f"**Moderator**: {escape_markdown_and_mentions(str(event.moderator))} ({event.moderator.id})")

        if event.reason:
            base.append(f"\n**Reason**: {escape_markdown_and_mentions(event.reason)}")

        return ''.join(base)

    @staticmethod
    def timed_action_expired(action, user, mod, creation, expiry, *, with_timestamp: bool = True) -> str:
        text = [f"[{format_timestamp(expiry)}] "] if with_timestamp else []

        text.append(f"**{action.capitalize()} expired**\n**User**: "
                    f"{MinimalisticFormat.format_user(user)}\n**Moderator**: {MinimalisticFormat.format_user(mod)}"
                    f"\n**Created at**: {discord.utils.format_dt(creation)}")
        return ''.join(text)

    @staticmethod
    def timeout_expired(event: AuditLogTimeoutEvent | MemberUpdateEvent, *, with_timestamp: bool = True) -> str:
        text = [f"[{format_timestamp(datetime.now(timezone.utc))}] "] if with_timestamp else []

        text.append(f"**Timeout expired**\n**User**: {MinimalisticFormat.format_user(event.member)}\n")

        if hasattr(event, 'moderator'):
            text.append(f"**Moderator**: {MinimalisticFormat.format_user(event.moderator)}")

        return ''.join(text)

    @staticmethod
    def bot_addition(bot, mod, time) -> str:
        safe_name = escape_markdown_and_mentions(str(bot))
        safe_mod_name = escape_markdown_and_mentions(str(mod))
        return f"[{format_timestamp(time)}] **Bot Add**"\
               f"\n**Bot**: {safe_name} ({bot.id})\n"\
               f"**Moderator**: {safe_mod_name} ({mod.id})"

    @staticmethod
    def join_leave(log_type: str, member) -> str:
        if log_type == "MEMBER_JOIN":
            msg = f"[{format_timestamp(member.joined_at)}]"\
                  f" **Member Join**: {discord.utils.escape_markdown(str(member))} ({member.id})\n"\
                  "__Account Creation Date__: "\
                  f"{discord.utils.format_dt(member.created_at)}"
        else:
            msg = f"[{format_timestamp(discord.utils.utcnow())}]"\
                  f" **Member Leave**: {discord.utils.escape_markdown(str(member))} ({member.id})"
        return msg

    @staticmethod
    def completed_screening(member, *, with_timestamp: bool = True):
        if with_timestamp:
            base = [f"[{format_timestamp(discord.utils.utcnow())}] "]
        else:
            base = []

        base.append(f"**Member Passed Screening**: {discord.utils.escape_markdown(str(member))} ({member.id})")
        return ''.join(base)

    @staticmethod
    def command_ran(ctx, *, with_timestamp: bool = True) -> str:
        if with_timestamp:
            base = [f"[{format_timestamp(ctx.message.created_at)}] "]
        else:
            base = []

        base.append(f"**Command Ran**\n**Command**: {ctx.command.qualified_name}\n**User**: "
                    f"{MinimalisticFormat.format_user(ctx.author)}\n"
                    f"**Channel**: {base_user_format(ctx.channel)}")

        return ''.join(base)

    @staticmethod
    def nick_change(member, previous: str, current: Optional[str], moderator=None, *, with_timestamp: bool = True):
        if with_timestamp:
            base = [f"[{format_timestamp(discord.utils.utcnow())}] "]
        else:
            base = []

        if current and previous:
            base.append(f"**Member Nickname Update**\n**Old Nickname**: {previous}\n**New Nickname**: {current}")
        elif previous is None and current is not None:
            base.append(f"**Member Nickname Add**\n**New Nickname**: {current}")
        elif current is None and previous is not None:
            base.append(f"**Member Nickname Removed**\n**Old Nickname**: {previous}")

        base.append(f"\n**Member**: {MinimalisticFormat.format_user(member)}")

        if moderator:
            base.append(f"\n**Moderator**: {MinimalisticFormat.format_user(moderator)}")

        return ''.join(base)

    @staticmethod
    def infraction_update(event: InfractionUpdateEvent, *,
                          with_timestamp: bool = True) -> str:
        if with_timestamp:
            base = [f"[{format_timestamp(discord.utils.utcnow())}] **Infraction Update**\n**ID**: {event.after.id}"]
        else:
            base = [f"**Infraction Update**\n**ID**: {event.after.id}"]

        if event.before.moderator_id != event.after.moderator_id:
            base.append(f"\n**Old Moderator**: {MinimalisticFormat.format_user(event.before.moderator)}"
                        f"\n**New Moderator**: {MinimalisticFormat.format_user(event.after.moderator)}")

        if event.before.reason != event.after.reason:
            base.append(f"\n**Old Reason**: {truncate_text(event.before.reason, limit=200)}"
                        f"\n**New Reason**: {truncate_text(event.after.reason, limit=200)}")

        return ''.join(base)

    @staticmethod
    def infraction_delete(event: InfractionDeleteEvent, *, with_timestamp: bool = True):
        if with_timestamp:
            base = [f"[{format_timestamp(discord.utils.utcnow())}] "]
        else:
            base = []

        base.append(f"**Infraction Delete**\n**ID**: {event.infraction.id}\n"
                    f"**Moderator**: {MinimalisticFormat.format_user(event.moderator)}")

        return ''.join(base)

    def format_message(self, *, with_timestamp: bool = True) -> str:
        """Formats a log entry."""
        log_action = log_actions[str(self.log_action).lower()]

        if with_timestamp:
            base = [f"[{format_timestamp(self.timestamp)}] "]
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

        embed.set_author(name=member, icon_url=member.avatar.url)
        embed.description = f"**User**: {member.mention} ({member.id}) \n**Created at**: "\
                            f"{natural_timedelta(member.created_at)}"
        return embed

    def format_message(self) -> discord.Embed:
        action = log_actions[str(self.log_action).lower()]
        embed = discord.Embed(title=action.title, color=action.color)
        reason = truncate_text(self.reason, 512)

        base = [f"**User**: {base_user_format(self.target)} <@!{self.target.id}>\n"
                f"**Moderator**: {base_user_format(self.moderator)} <@!{self.moderator.id}>"]

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
    def timeout_expired(event: AuditLogTimeoutEvent | MemberUpdateEvent) -> discord.Embed:
        embed = discord.Embed(description=f"Timeout for {base_user_format(event.member)} expired")

        if hasattr(event, 'moderator'):
            embed.add_field(name="Moderator", value=base_user_format(event.moderator))

        return embed

    @staticmethod
    def role_change(event: MemberRolesUpdateEvent) -> discord.Embed:
        embed = discord.Embed(title="Role Change", color=discord.Color.dark_gold(),
                              description=f"User: {event.after.mention} ({event.after.id})")

        if event.entry:
            removed = event.entry.changes.before.roles
            added = event.entry.changes.after.roles
            time = event.entry.created_at
        else:
            added = event.added_roles
            removed = event.removed_roles
            time = discord.utils.utcnow()

        if event.moderator:
            embed.add_field(name="Moderator", value=base_user_format(event.moderator))

        if added:
            added = "".join(r.mention for r in added)
            embed.description += f"\nAdded: {added}"

        if removed:
            removed = "".join(r.mention for r in removed)
            embed.description += f"\nRemoved: {removed}"

        embed.timestamp = time
        return embed

    @staticmethod
    def role_addition(event: MemberRolesUpdateEvent):
        return EmbedFormat.role_change(event)

    @staticmethod
    def command_ran(ctx) -> discord.Embed:
        embed = discord.Embed(title="Command Ran", color=0xf74b06, timestamp=ctx.message.created_at)
        user = ctx.author
        embed.description = f"**Command**: {ctx.command.qualified_name}\n**User**: {user.mention} ({user.id})"\
                            f"\n**Channel**: {ctx.channel.mention} ({ctx.channel.id})"
        return embed

    @staticmethod
    def nick_change(member, previous: str, current: Optional[str], moderator=None) -> discord.Embed:
        embed = discord.Embed(color=discord.Color.blurple(), timestamp=discord.utils.utcnow())

        if current and previous:
            embed.title = "Member Nickname Update"
            embed.description = f"**Old Nickname**: {previous}\n**New Nickname**: {current}"
        elif previous is None and current is not None:
            embed.title = "Member Nickname Add"
            embed.description = f"**New Nickname**: {current}"
        elif current is None and previous is not None:
            embed.title = "Member Nickname Removed"
            embed.description = f"**Old Nickname**: {previous}"

        embed.description += f"\n**Member**: {base_user_format(member)}"

        if moderator:
            embed.add_field(name="Moderator", value=base_user_format(moderator))

        return embed

    @staticmethod
    def completed_screening(member: discord.Member):
        return discord.Embed(title="Member Passed Screening", description=f"**Member**: {base_user_format(member)}",
                             color=discord.Color.blurple(), timestamp=discord.utils.utcnow())

    @staticmethod
    def infraction_update(event: InfractionUpdateEvent) -> discord.Embed:
        embed = discord.Embed(color=discord.Color.yellow(), timestamp=discord.utils.utcnow(), title="Infraction Update")
        embed.set_footer(text=f"Infraction ID: {event.after.id}")

        if event.before.moderator_id != event.after.moderator_id:
            embed.add_field(name="Moderator",
                            value=f"**Old**: {base_user_format(event.before.moderator)}\n**New**: "
                                  f"{base_user_format(event.after.moderator)}")

        if event.before.reason != event.after.reason:
            embed.add_field(name="Reason",
                            value=f"**Old**: {truncate_text(event.before.reason, limit=200)}\n**New**: "
                                  f"{truncate_text(event.after.reason, limit=200)}")

        return embed

    @staticmethod
    def infraction_delete(event: InfractionDeleteEvent) -> discord.Embed:
        embed = discord.Embed(color=discord.Color.red(),
                              title="Infraction Delete",
                              description=f"**ID**: {event.infraction.id}\n**Moderator**: "
                                          f"{base_user_format(event.moderator)}")

        return embed
