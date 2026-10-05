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

from typing import TYPE_CHECKING

import discord

from lightning.formatters import truncate_text
from lightning.utils.helpers import Emoji
from lightning.utils.modlogformats.base import (BaseFormat,
                                                escape_markdown_and_mentions,
                                                log_actions, modlog_format)
from lightning.utils.time import get_utc_timestamp

if TYPE_CHECKING:
    from lightning.events import (AuditLogTimeoutEvent, InfractionDeleteEvent,
                                  InfractionUpdateEvent,
                                  MemberRolesUpdateEvent, MemberUpdateEvent)


@modlog_format("emoji")
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
