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

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import discord

from lightning.formatters import truncate_text
from lightning.utils.modlogformats.base import (BaseFormat, base_user_format,
                                                escape_markdown_and_mentions,
                                                format_timestamp, log_actions,
                                                modlog_format)

if TYPE_CHECKING:
    from lightning.events import (AuditLogTimeoutEvent, InfractionDeleteEvent,
                                  InfractionUpdateEvent,
                                  MemberRolesUpdateEvent, MemberUpdateEvent)


@modlog_format("minimal")
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
            if isinstance(self.expiry, datetime):
                # TZINFO should not be stripped at this point.
                expy = discord.utils.format_dt(self.expiry)
            else:
                expy = self.expiry

            base.append(f"\n**Expiry**: {expy}")

        base.append(f"\n**Reason**: {escape_markdown_and_mentions(self.reason)}")
        return ''.join(base)
