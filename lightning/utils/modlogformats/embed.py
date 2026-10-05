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

from typing import TYPE_CHECKING, Optional

import discord

from lightning.formatters import truncate_text
from lightning.utils.modlogformats.base import (BaseFormat, base_user_format,
                                                log_actions, modlog_format)
from lightning.utils.time import natural_timedelta

if TYPE_CHECKING:
    from lightning.events import (AuditLogTimeoutEvent, InfractionDeleteEvent,
                                  InfractionUpdateEvent,
                                  MemberRolesUpdateEvent, MemberUpdateEvent)


@modlog_format("embed")
class EmbedFormat(BaseFormat):
    @staticmethod
    def join_leave(log_type: str, member: discord.Member):
        embed = discord.Embed()

        if log_type == "MEMBER_JOIN":
            embed.title = "Member Join"
            embed.color = discord.Color.green()
        else:
            embed.title = "Member Leave"
            embed.color = discord.Color.red()

        embed.set_author(name=member, icon_url=member.display_avatar.url)
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
