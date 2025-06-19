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

import asyncio
import logging
from datetime import timedelta
from typing import Callable, Optional

import discord

from lightning import LightningBot, LightningCog
from lightning.enums import ActionType
from lightning.events import (AuditLogModAction, AuditLogTimeoutEvent,
                              GuildRoleDeleteEvent, MemberRolesUpdateEvent,
                              MemberRoleUpdateEvent, MemberUpdateEvent)

log = logging.getLogger(__name__)


def match_attribute(attr, before, after):
    def check(entry):
        return getattr(entry.before, attr, None) == before and getattr(entry.after, attr, None) == after
    return check


def role_check(before, after):
    def check(entry: discord.AuditLogEntry):
        added = [role for role in after.roles if role not in before.roles]
        removed = [role for role in before.roles if role not in after.roles]
        return entry.target.id == before.id and hasattr(entry.changes.before, "roles") \
            and hasattr(entry.changes.after, "roles") and \
            all(r in entry.changes.before.roles for r in removed) and \
            all(r in entry.changes.after.roles for r in added)
    return check


def guild_role_check(role):
    def check(entry: discord.AuditLogEntry):
        return role.id == entry.target.id  # getattr(entry.target, "id", None)
    return check


class ListenerEvents(LightningCog):
    """Cog that's meant to give us nicer events to use.

    Based off of Mousey's event system"""
    def __init__(self, bot: LightningBot):
        super().__init__(bot)
        self.ignored = set()
        self._cached_audit_logs: dict[int, list[discord.AuditLogEntry]] = {}

    # TODO: Don't fetch entries if no logging is enabled???

    # 10 second cache for audit logs to reduce the number of requests to the audit log endpoint
    @LightningCog.listener('on_audit_log_entry_create')
    async def cache_audit_logs(self, entry: discord.AuditLogEntry):
        # I don't care about anything else other than the actions below
        if entry.action not in (discord.AuditLogAction.member_update, discord.AuditLogAction.role_delete,
                                discord.AuditLogAction.member_role_update):
            return

        if entry.guild.id not in self._cached_audit_logs:
            self._cached_audit_logs[entry.guild.id] = [entry]
        else:
            self._cached_audit_logs[entry.guild.id].append(entry)

        self.bot.loop.call_later(10, self._cached_audit_logs[entry.guild.id].remove, entry)

    async def fetch_audit_log_entry(self, guild: discord.Guild, action: discord.AuditLogAction, *,
                                    target: Optional[discord.abc.Snowflake] = None, limit: int = 50,
                                    check: Optional[Callable] = None) -> Optional[discord.AuditLogEntry]:
        for entry in self._cached_audit_logs.get(guild.id, []):
            if entry.action is not action:
                continue

            td = discord.utils.utcnow() - entry.created_at
            if td < timedelta(seconds=10):
                if target is not None and entry.target.id == target.id:
                    return entry

                if check is not None and check(entry):
                    return entry

    async def check_and_wait(self, guild: discord.Guild, *, timeout=0.5) -> bool:
        """Checks if the bot has permissions to view the audit log and waits if the bot does have permission."""
        await self.bot.wait_until_ready()  # Might make this optional...

        if not guild.me:
            return False

        if not guild.me.guild_permissions.view_audit_log:
            # There's no point to wait if we don't have perms
            return False

        await asyncio.sleep(timeout)
        return True

    async def resolve_removed_target(self, entry: discord.AuditLogEntry):
        if isinstance(entry.target, (discord.User, discord.Member)):
            return entry.target

        try:
            await self.bot.fetch_user(entry.target.id)
        except discord.HTTPException:
            return entry.target

    # Moderation Audit Log Integration Events
    @LightningCog.listener('on_audit_log_entry_create')
    async def on_member_kick(self, entry: discord.AuditLogEntry):
        if entry.action is not discord.AuditLogAction.kick:
            return

        if entry.user_id == self.bot.user.id:
            # Should already be logged
            return

        if entry.user is None:
            log.info(f"Creating AuditLogModAction event: entry.user={entry.user} entry.user_id={entry.user_id}"
                     f"entry.user bot lookup={self.bot.get_user(entry.user_id)}"
                     f"entry.user guild lookup={entry.guild.get_member(entry.user_id)}")
            entry.user = discord.Object(entry.user_id)

        # entry.target is discord.User maybe?
        event = AuditLogModAction("KICK", entry.target, entry, guild=entry.guild)
        self.bot.dispatch("lightning_member_kick", event)

    @LightningCog.listener('on_audit_log_entry_create')
    async def on_member_ban(self, entry: discord.AuditLogEntry):
        if entry.action is not discord.AuditLogAction.ban:
            return

        if entry.user_id == self.bot.user.id:
            # should be logged
            return

        if entry.user is None:
            log.info(f"Creating AuditLogModAction event: entry.user={entry.user} entry.user_id={entry.user_id}"
                     f"entry.user bot lookup={self.bot.get_user(entry.user_id)}"
                     f"entry.user guild lookup={entry.guild.get_member(entry.user_id)}")
            entry.user = discord.Object(entry.user_id)

        event = AuditLogModAction("BAN", entry.target, entry, guild=entry.guild)
        self.bot.dispatch("lightning_member_ban", event)

    @LightningCog.listener('on_audit_log_entry_create')
    async def on_member_unban(self, entry: discord.AuditLogEntry):
        if entry.action is not discord.AuditLogAction.unban:
            return

        if entry.user_id == self.bot.user.id:
            # should be logged
            return

        if entry.user is None:
            log.info(f"Creating AuditLogModAction event: entry.user={entry.user} entry.user_id={entry.user_id}"
                     f"entry.user bot lookup={self.bot.get_user(entry.user_id)}"
                     f"entry.user guild lookup={entry.guild.get_member(entry.user_id)}")
            entry.user = discord.Object(entry.user_id)

        event = AuditLogModAction("UNBAN", entry.target, entry, guild=entry.guild)
        self.bot.dispatch("lightning_member_unban", event)

    # Member events with optional audit log information
    @LightningCog.listener('on_member_update')
    async def on_member_nick_change(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick:
            return

        check = await self.check_and_wait(before.guild)

        if check is True:
            entry = await self.fetch_audit_log_entry(before.guild, discord.AuditLogAction.member_update, target=after,
                                                     check=match_attribute("nick", before.nick, after.nick))
        else:
            entry = None

        self.bot.dispatch("lightning_member_nick_change", MemberUpdateEvent(before, after, entry))

    @LightningCog.listener('on_member_update')
    async def on_member_role_change(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        check = await self.check_and_wait(before.guild)

        if check is True:
            entry = await self.fetch_audit_log_entry(before.guild, discord.AuditLogAction.member_role_update,
                                                     target=before, check=role_check(before, after))
        else:
            entry = None

        self.bot.dispatch("lightning_member_role_change", MemberRolesUpdateEvent(before, after, entry))

    # Member events that don't need audit logs
    @LightningCog.listener('on_member_update')
    async def on_member_passed_screening(self, before: discord.Member, after: discord.Member):
        if before.pending is True and after.pending is False:
            self.bot.dispatch("lightning_member_passed_screening", after)

    # Guild events with Audit Log Integration
    @LightningCog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        check = await self.check_and_wait(role.guild)

        if check is True:
            entry = await self.fetch_audit_log_entry(role.guild, discord.AuditLogAction.role_delete,
                                                     target=role, check=guild_role_check(role))
        else:
            entry = None

        self.bot.dispatch("lightning_guild_role_delete", GuildRoleDeleteEvent(role, entry))

    # Dispatches role_add and role_remove events.
    @LightningCog.listener()
    async def on_lightning_member_role_change(self, event: MemberRolesUpdateEvent):
        for role in event.added_roles:
            self.bot.dispatch("lightning_member_role_add", MemberRoleUpdateEvent(role, event.entry))

        for role in event.removed_roles:
            self.bot.dispatch("lightning_member_role_remove", MemberRoleUpdateEvent(role, event.entry))

    @LightningCog.listener('on_audit_log_entry_create')
    async def on_member_timeout(self, entry: discord.AuditLogEntry):
        if entry.action is not discord.AuditLogAction.member_update:
            return

        if not hasattr(entry.before, "timed_out_until"):
            return

        if entry.before.timed_out_until is None and entry.after.timed_out_until is not None:
            if f"{entry.guild.id}:on_lightning_member_timeout:{entry.target.id}" in self.ignored:
                return

            event = AuditLogTimeoutEvent(ActionType.TIMEOUT, entry, guild=entry.guild)
            event.action.expiry = entry.after.timed_out_until
            self.bot.dispatch("lightning_member_timeout", event)
        elif entry.before.timed_out_until is not None and entry.after.timed_out_until is None:
            self.bot.dispatch("lightning_member_timeout_remove", AuditLogTimeoutEvent(ActionType.UNTIMEOUT,
                                                                                      entry, guild=entry.guild))


async def setup(bot: LightningBot) -> None:
    await bot.add_cog(ListenerEvents(bot))
