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

import discord

from lightning.events import (MemberJoinEvent, MemberLeaveEvent,
                              MemberRolesUpdateEvent, MemberScreeningEvent,
                              MemberUpdateEvent)
from lightning.formatters import base_user_format, escape_markdown_and_mentions
from lightning.utils.helpers import Emoji
from lightning.utils.modlogformats.base import FormatContext, Renderer, renders
from lightning.utils.time import natural_timedelta


def format_user(user) -> str:
    """Used by the minimal format. Users we can't resolve just show their ID."""
    if hasattr(user, 'name'):
        return f"{escape_markdown_and_mentions(str(user))} ({user.id})"
    return f"ID: {user.id}"


@renders(MemberJoinEvent)
class MemberJoin(Renderer[MemberJoinEvent]):
    def mentions(self):
        return [self.event.member]

    def emoji(self) -> str:
        member = self.event.member
        return f"{Emoji.member_join} **Member Join**: {member.mention} | "\
               f"{escape_markdown_and_mentions(str(member))}\n"\
               f"\N{CLOCK FACE FOUR OCLOCK} __Account Creation__: {discord.utils.format_dt(member.created_at)}\n"\
               f"\N{LABEL} __User ID__: {member.id}"

    def minimal(self, ctx: FormatContext) -> str:
        member = self.event.member
        return f"{self.stamp(ctx, member.joined_at)}**Member Join**: {discord.utils.escape_markdown(str(member))} "\
               f"({member.id})\n__Account Creation Date__: {discord.utils.format_dt(member.created_at)}"

    def embed(self) -> discord.Embed:
        member = self.event.member
        embed = discord.Embed(title="Member Join", color=discord.Color.green())
        embed.set_author(name=member, icon_url=member.display_avatar.url)
        embed.description = f"**User**: {member.mention} ({member.id}) \n**Created at**: "\
                            f"{natural_timedelta(member.created_at)}"
        return embed


@renders(MemberLeaveEvent)
class MemberLeave(Renderer[MemberLeaveEvent]):
    def mentions(self):
        return [self.event.member]

    def emoji(self) -> str:
        member = self.event.member
        return f"{Emoji.member_leave} **Member Leave**: {member.mention} | "\
               f"{escape_markdown_and_mentions(str(member))}\n"\
               f"\N{LABEL} __User ID__: {member.id}"

    def minimal(self, ctx: FormatContext) -> str:
        member = self.event.member
        return f"{self.stamp(ctx)}**Member Leave**: {discord.utils.escape_markdown(str(member))} ({member.id})"

    def embed(self) -> discord.Embed:
        member = self.event.member
        embed = discord.Embed(title="Member Leave", color=discord.Color.red())
        embed.set_author(name=member, icon_url=member.display_avatar.url)
        embed.description = f"**User**: {member.mention} ({member.id}) \n**Created at**: "\
                            f"{natural_timedelta(member.created_at)}"
        return embed


@renders(MemberScreeningEvent)
class MemberScreening(Renderer[MemberScreeningEvent]):
    def mentions(self):
        return [self.event.member]

    def emoji(self) -> str:
        member = self.event.member
        return f"\N{PASSPORT CONTROL} **Member Completed Screening** {member.mention} | "\
               f"({escape_markdown_and_mentions(str(member))}"

    def minimal(self, ctx: FormatContext) -> str:
        member = self.event.member
        return f"{self.stamp(ctx)}**Member Passed Screening**: {discord.utils.escape_markdown(str(member))} "\
               f"({member.id})"

    def embed(self) -> discord.Embed:
        return discord.Embed(title="Member Passed Screening",
                             description=f"**Member**: {base_user_format(self.event.member)}",
                             color=discord.Color.blurple(), timestamp=discord.utils.utcnow())


@renders(MemberUpdateEvent)
class NickChange(Renderer[MemberUpdateEvent]):
    def mentions(self):
        return [self.event.after]

    @property
    def previous(self):
        return self.event.before.nick

    @property
    def current(self):
        return self.event.after.nick

    def emoji(self) -> str:
        member, previous, current = self.event.after, self.previous, self.current
        if previous is None and current is not None:
            change = f"\N{LABEL} __Nickname added__: None -> {current}"
        elif previous is not None and current is not None:
            change = f"\N{LABEL} __Nickname changed__: {previous} -> {current}"
        else:
            change = f"\N{LABEL} __Nickname removed__: {previous} -> None"

        msg = [f"\N{INFORMATION SOURCE} **Member update**: {member} | {member.id} {change}"]

        if self.event.moderator:
            msg.append(f"\n\N{BLUE BOOK} __Moderator__: "
                       f"{escape_markdown_and_mentions(str(self.event.moderator))} ({self.event.moderator.id})")

        return ''.join(msg)

    def minimal(self, ctx: FormatContext) -> str:
        base = [self.stamp(ctx)]

        if self.current and self.previous:
            base.append(f"**Member Nickname Update**\n**Old Nickname**: {self.previous}\n"
                        f"**New Nickname**: {self.current}")
        elif self.previous is None and self.current is not None:
            base.append(f"**Member Nickname Add**\n**New Nickname**: {self.current}")
        elif self.current is None and self.previous is not None:
            base.append(f"**Member Nickname Removed**\n**Old Nickname**: {self.previous}")

        base.append(f"\n**Member**: {format_user(self.event.after)}")

        if self.event.moderator:
            base.append(f"\n**Moderator**: {format_user(self.event.moderator)}")

        return ''.join(base)

    def embed(self) -> discord.Embed:
        embed = discord.Embed(color=discord.Color.blurple(), timestamp=discord.utils.utcnow())

        if self.current and self.previous:
            embed.title = "Member Nickname Update"
            embed.description = f"**Old Nickname**: {self.previous}\n**New Nickname**: {self.current}"
        elif self.previous is None and self.current is not None:
            embed.title = "Member Nickname Add"
            embed.description = f"**New Nickname**: {self.current}"
        elif self.current is None and self.previous is not None:
            embed.title = "Member Nickname Removed"
            embed.description = f"**Old Nickname**: {self.previous}"

        embed.description += f"\n**Member**: {base_user_format(self.event.after)}"

        if self.event.moderator:
            embed.add_field(name="Moderator", value=base_user_format(self.event.moderator))

        return embed


@renders(MemberRolesUpdateEvent)
class RoleChange(Renderer[MemberRolesUpdateEvent]):
    # If we have the audit log entry, it's the best source for what changed
    @property
    def added(self):
        return self.event.entry.changes.after.roles if self.event.entry else self.event.added_roles

    @property
    def removed(self):
        return self.event.entry.changes.before.roles if self.event.entry else self.event.removed_roles

    def emoji(self) -> str:
        event, added, removed = self.event, self.added, self.removed

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

        msg = [f"\N{INFORMATION SOURCE} **Member update**: {escape_markdown_and_mentions(str(event.after))} | "
               f"{event.after.id} \n👑__Role change__: {', '.join(roles)}"]

        if event.moderator:
            msg.append(f"\n\N{BLUE BOOK} __Moderator__: "
                       f"{escape_markdown_and_mentions(str(event.moderator))} ({event.moderator.id})")

        return ''.join(msg)

    def minimal(self, ctx: FormatContext) -> str:
        event = self.event
        time = event.entry.created_at if event.entry else discord.utils.utcnow()

        base = [f"{self.stamp(ctx, time)}**Role Change**\n"
                f"**User**: {escape_markdown_and_mentions(str(event.after))} ({event.after.id})\n"]

        for role in event.added_roles:
            base.append(f"**Role Added**: {escape_markdown_and_mentions(str(role))} ({role.id})\n")

        for role in event.removed_roles:
            base.append(f"**Role Removed**: {escape_markdown_and_mentions(str(role))} ({role.id})\n")

        if event.moderator is not None:
            base.append(f"**Moderator**: {escape_markdown_and_mentions(str(event.moderator))} ({event.moderator.id})")

        if event.reason:
            base.append(f"\n**Reason**: {escape_markdown_and_mentions(event.reason)}")

        return ''.join(base)

    def embed(self) -> discord.Embed:
        event = self.event
        embed = discord.Embed(title="Role Change", color=discord.Color.dark_gold(),
                              description=f"User: {event.after.mention} ({event.after.id})")

        if event.moderator:
            embed.add_field(name="Moderator", value=base_user_format(event.moderator))

        if self.added:
            embed.description += f"\nAdded: {''.join(r.mention for r in self.added)}"

        if self.removed:
            embed.description += f"\nRemoved: {''.join(r.mention for r in self.removed)}"

        embed.timestamp = event.entry.created_at if event.entry else discord.utils.utcnow()
        return embed
