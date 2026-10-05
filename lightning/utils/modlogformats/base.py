"""
Lightning.py - A Discord bot
Copyright (C) 2019-present LightSage

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
from datetime import datetime
from typing import (TYPE_CHECKING, Any, Callable, Literal, Optional, Type,
                    TypeVar, Union, overload)

import discord

from lightning.models import Action

if TYPE_CHECKING:
    from lightning import LightningContext
    from lightning.events import (AuditLogTimeoutEvent, InfractionDeleteEvent,
                                  InfractionUpdateEvent,
                                  MemberRolesUpdateEvent, MemberUpdateEvent)

FormatName = Literal["emoji", "minimal", "embed"]


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


# Registry time! Each format class tags itself with @modlog_format("name") so we
# never have to hand-maintain a lookup table, and the cog doesn't need to know
# which classes exist.
_formats: dict[str, Type[BaseFormat]] = {}
_F = TypeVar("_F", bound=Type[BaseFormat])


def modlog_format(name: FormatName) -> Callable[[_F], _F]:
    def decorator(cls: _F) -> _F:
        _formats[name] = cls
        return cls
    return decorator


def parse_format_setting(setting: str) -> tuple[FormatName, dict[str, bool]]:
    """Turns the format we store in the db into a format name + the kwargs it accepts.

    Only the minimal format cares about timestamps, so that's the only one that gets a kwarg.
    """
    if setting in ("minimal with timestamp", "minimal without timestamp"):
        return "minimal", {"with_timestamp": setting != "minimal without timestamp"}
    return setting, {}  # type: ignore[return-value]


# The overloads below are purely for type checkers. They spell out exactly what each
# format wants for each event (they're not all the same, ex. timed_action_expired),
# so passing with_timestamp to emoji or embed gets flagged. The real function at the
# bottom just looks the method up by name.


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["command_ran"],
                 ctx: LightningContext,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["command_ran"],
                 ctx: LightningContext) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["command_ran"],
                 ctx: LightningContext) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["role_change"],
                 event: MemberRolesUpdateEvent,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["role_change"],
                 event: MemberRolesUpdateEvent) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["role_change"],
                 event: MemberRolesUpdateEvent) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["nick_change"],
                 member: discord.Member,
                 previous: str,
                 current: Optional[str],
                 moderator: Any = ...,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["nick_change"],
                 member: discord.Member,
                 previous: str,
                 current: Optional[str],
                 moderator: Any = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["nick_change"],
                 member: discord.Member,
                 previous: str,
                 current: Optional[str],
                 moderator: Any = ...) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["timed_action_expired"],
                 action: str,
                 user: Any,
                 mod: Any,
                 creation: datetime,
                 expiry: datetime,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["timed_action_expired"],
                 action: str,
                 user: Any,
                 mod: Any,
                 creation: datetime) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["timed_action_expired"],
                 action: str,
                 moderator: Any,
                 user: Any,
                 created_at: datetime) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["join_leave"],
                 log_type: str,
                 member: discord.Member) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["join_leave"],
                 log_type: str,
                 member: discord.Member) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["join_leave"],
                 log_type: str,
                 member: discord.Member) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["completed_screening"],
                 member: discord.Member,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["completed_screening"],
                 member: discord.Member) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["completed_screening"],
                 member: discord.Member) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["timeout_expired"],
                 event: AuditLogTimeoutEvent | MemberUpdateEvent,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["timeout_expired"],
                 event: AuditLogTimeoutEvent | MemberUpdateEvent) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["timeout_expired"],
                 event: AuditLogTimeoutEvent | MemberUpdateEvent) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["infraction_update"],
                 event: InfractionUpdateEvent,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["infraction_update"],
                 event: InfractionUpdateEvent) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["infraction_update"],
                 event: InfractionUpdateEvent) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["infraction_delete"],
                 event: InfractionDeleteEvent,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["infraction_delete"],
                 event: InfractionDeleteEvent) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["infraction_delete"],
                 event: InfractionDeleteEvent) -> discord.Embed:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["bot_addition"],
                 bot: discord.Member,
                 mod: Any,
                 time: datetime) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["bot_addition"],
                 bot: discord.Member,
                 mod: Any) -> str:
    ...


@overload
def format_event(fmt_name: Literal["minimal"], event_name: Literal["from_action"],
                 action: Action,
                 *,
                 with_timestamp: bool = ...) -> str:
    ...


@overload
def format_event(fmt_name: Literal["emoji"], event_name: Literal["from_action"],
                 action: Action) -> str:
    ...


@overload
def format_event(fmt_name: Literal["embed"], event_name: Literal["from_action"],
                 action: Action) -> discord.Embed:
    ...


def format_event(fmt_name: FormatName, event_name: str, *args: Any, **kwargs: Any) -> Union[str, discord.Embed]:
    cls = _formats[fmt_name]
    if event_name == "from_action":
        # Actions are formatted through an instance rather than a static method
        action, *_ = args
        return cls.from_action(action).format_message(**kwargs)
    return getattr(cls, event_name)(*args, **kwargs)
