"""
Lightning.py - A Discord bot
Copyright (C) 2019-present Célveren

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
from typing import Union

import discord

from lightning.events import (AuditLogTimeoutEvent, InfractionDeleteEvent,
                              InfractionUpdateEvent, TimedActionExpiredEvent)
from lightning.formatters import (base_user_format,
                                  escape_markdown_and_mentions, truncate_text)
from lightning.models import Action
from lightning.modlogformats.base import FormatContext, Renderer, renders
from lightning.modlogformats.member import format_user
from lightning.utils.time import get_utc_timestamp


@dataclass
class CompactModAction:
    tense: str
    emoji: str
    title: str
    color: Union[discord.Color, int]


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


# This one is keyed on Action instead of one of the event classes. Every moderation event
# (ban, kick, mute, automod, etc.) carries an Action, so the cog just hands that over.
@renders(Action)
class ModAction(Renderer[Action]):
    def __init__(self, action: Action) -> None:
        super().__init__(action)
        if not action.is_logged():
            raise ValueError("Only actions that have been logged as an infraction can be rendered")

        self.info = log_actions[str(action.action).lower()]
        self.reason = action.reason or "no reason given"

    def mentions(self):
        return [self.event.target, self.event.moderator]

    def _target_with_expiry(self) -> str:
        target = self.event.target
        if target is None:
            return ""

        for_expiry = f" for {self.event.expiry}" if self.event.expiry else ""

        mention = target.mention if hasattr(target, 'mention') else f"<@!{target.id}>"
        if isinstance(target, discord.Object):
            return mention
        return f"{mention}{for_expiry} | {discord.utils.escape_markdown(str(target))}"

    def emoji(self) -> str:
        event = self.event
        message = [f"{self.info.emoji} **{self.info.title}**: {event.moderator.mention} {self.info.tense} ",
                   self._target_with_expiry()]

        if hasattr(event.target, 'id'):
            message.append(f"\n\N{LABEL} __User ID__: {event.target.id}")

        message.append(f"\n\N{PENCIL}\N{VARIATION SELECTOR-16} __Reason__: \"{self.reason}\"")
        return ''.join(message)

    def minimal(self, ctx: FormatContext) -> str:
        event = self.event
        base = [f"{self.stamp(ctx, event.timestamp)}**{self.info.title}** | Infraction ID {event.infraction_id}"
                f"\n**User**: {format_user(event.target)}\n**Moderator**: {format_user(event.moderator)}"]

        if event.expiry:
            if isinstance(event.expiry, datetime):
                # TZINFO should not be stripped at this point.
                expy = discord.utils.format_dt(event.expiry)
            else:
                expy = event.expiry

            base.append(f"\n**Expiry**: {expy}")

        base.append(f"\n**Reason**: {escape_markdown_and_mentions(self.reason)}")
        return ''.join(base)

    def embed(self) -> discord.Embed:
        event = self.event
        embed = discord.Embed(title=self.info.title, color=self.info.color)
        reason = truncate_text(self.reason, 512)

        base = [f"**User**: {base_user_format(event.target)} <@!{event.target.id}>\n"
                f"**Moderator**: {base_user_format(event.moderator)} <@!{event.moderator.id}>"]

        if event.expiry:
            base.append(f"\n**Expiry**: {event.expiry}")

        base.append(f"\n**Reason**: {discord.utils.escape_markdown(reason)}")
        embed.description = ''.join(base)
        embed.set_footer(text=f"Infraction ID: {event.infraction_id}")
        embed.timestamp = event.timestamp
        return embed


@renders(TimedActionExpiredEvent)
class TimedActionExpired(Renderer[TimedActionExpiredEvent]):
    def mentions(self):
        return [self.event.user, self.event.moderator]

    def emoji(self) -> str:
        event = self.event
        action = event.action
        msg = [f"\N{WARNING SIGN} **{action.capitalize()} expired**: <@!{event.user.id}>"]

        if hasattr(event.user, 'name'):
            msg.append(f" | {discord.utils.escape_mentions(str(event.user))}")

        msg.append(f"\nTime{action} was made by <@!{event.moderator.id}>")

        if hasattr(event.moderator, 'name'):
            msg.append(f" | {discord.utils.escape_mentions(str(event.moderator))}")

        msg.append(f" at {get_utc_timestamp(event.created_at)}")
        return ''.join(msg)

    def minimal(self, ctx: FormatContext) -> str:
        event = self.event
        return f"{self.stamp(ctx, event.expiry)}**{event.action.capitalize()} expired**\n"\
               f"**User**: {format_user(event.user)}\n**Moderator**: {format_user(event.moderator)}"\
               f"\n**Created at**: {discord.utils.format_dt(event.created_at)}"

    def embed(self) -> discord.Embed:
        event = self.event
        embed = discord.Embed(description=f"Time {event.action} for {base_user_format(event.user)} expired")
        embed.add_field(name="Moderator", value=base_user_format(event.moderator))
        embed.timestamp = event.created_at
        embed.set_footer(text=f"Time {event.action} was made at")
        return embed


@renders(AuditLogTimeoutEvent)
class TimeoutExpired(Renderer[AuditLogTimeoutEvent]):
    def mentions(self):
        return [self.event.member]

    def emoji(self) -> str:
        event = self.event
        text = [f"\N{WARNING SIGN} **Timeout expired** <@!{event.member.id}>"]

        if event.moderator:
            text.append(f"\n\N{BLUE BOOK} __Moderator__: "
                        f"{escape_markdown_and_mentions(str(event.moderator))} ({event.moderator.id})")

        return ''.join(text)

    def minimal(self, ctx: FormatContext) -> str:
        text = [f"{self.stamp(ctx)}**Timeout expired**\n**User**: {format_user(self.event.member)}\n"]

        if self.event.moderator:
            text.append(f"**Moderator**: {format_user(self.event.moderator)}")

        return ''.join(text)

    def embed(self) -> discord.Embed:
        embed = discord.Embed(description=f"Timeout for {base_user_format(self.event.member)} expired")

        if self.event.moderator:
            embed.add_field(name="Moderator", value=base_user_format(self.event.moderator))

        return embed


@renders(InfractionUpdateEvent)
class InfractionUpdate(Renderer[InfractionUpdateEvent]):
    @property
    def moderator_changed(self) -> bool:
        return self.event.before.moderator_id != self.event.after.moderator_id

    @property
    def reason_changed(self) -> bool:
        return self.event.before.reason != self.event.after.reason

    def emoji(self) -> str:
        event = self.event
        base = [f"\N{MEMO} **Infraction update**: ID: {event.after.id}"]

        if self.moderator_changed:
            base.append(f"\n__Old Moderator__: <@!{event.before.moderator_id}>"
                        f"\n__New Moderator__: <@!{event.after.moderator_id}>")

        if self.reason_changed:
            base.append(f"\n__Old Reason__: {truncate_text(event.before.reason, limit=200)}"
                        f"\n__New Reason__: {truncate_text(event.after.reason, limit=200)}")

        return ''.join(base)

    def minimal(self, ctx: FormatContext) -> str:
        event = self.event
        base = [f"{self.stamp(ctx)}**Infraction Update**\n**ID**: {event.after.id}"]

        if self.moderator_changed:
            base.append(f"\n**Old Moderator**: {format_user(event.before.moderator)}"
                        f"\n**New Moderator**: {format_user(event.after.moderator)}")

        if self.reason_changed:
            base.append(f"\n**Old Reason**: {truncate_text(event.before.reason, limit=200)}"
                        f"\n**New Reason**: {truncate_text(event.after.reason, limit=200)}")

        return ''.join(base)

    def embed(self) -> discord.Embed:
        event = self.event
        embed = discord.Embed(color=discord.Color.yellow(), timestamp=discord.utils.utcnow(), title="Infraction Update")
        embed.set_footer(text=f"Infraction ID: {event.after.id}")

        if self.moderator_changed:
            embed.add_field(name="Moderator",
                            value=f"**Old**: {base_user_format(event.before.moderator)}\n**New**: "
                                  f"{base_user_format(event.after.moderator)}")

        if self.reason_changed:
            embed.add_field(name="Reason",
                            value=f"**Old**: {truncate_text(event.before.reason, limit=200)}\n**New**: "
                                  f"{truncate_text(event.after.reason, limit=200)}")

        return embed


@renders(InfractionDeleteEvent)
class InfractionDelete(Renderer[InfractionDeleteEvent]):
    def mentions(self):
        return [self.event.moderator]

    def emoji(self) -> str:
        return f"\N{PUT LITTER IN ITS PLACE SYMBOL} **Infraction deleted** "\
               f"{self.event.moderator.mention} deleted #{self.event.infraction.id}"

    def minimal(self, ctx: FormatContext) -> str:
        return f"{self.stamp(ctx)}**Infraction Delete**\n**ID**: {self.event.infraction.id}\n"\
               f"**Moderator**: {format_user(self.event.moderator)}"

    def embed(self) -> discord.Embed:
        return discord.Embed(color=discord.Color.red(), title="Infraction Delete",
                             description=f"**ID**: {self.event.infraction.id}\n**Moderator**: "
                                         f"{base_user_format(self.event.moderator)}")
