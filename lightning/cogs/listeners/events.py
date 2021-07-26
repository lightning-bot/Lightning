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
import asyncio
from datetime import timedelta
from typing import Optional

import discord

from lightning import LightningBot, LightningCog
from lightning.events import (AuditLogModAction, GuildRoleDeleteEvent,
                              MemberRolesUpdateEvent, MemberRoleUpdateEvent,
                              MemberUpdateEvent)


def match_attribute(attr, before, after):
    def check(entry):
        return getattr(entry.before, attr, None) == before and getattr(entry.after, attr, None) == after
    return check


def role_check(before, after):
    def check(entry):
        added = [role for role in after.roles if role not in before.roles]
        removed = [role for role in before.roles if role not in after.roles]
        return entry.target.id == before.id and hasattr(entry.changes.before, "roles") \
            and hasattr(entry.changes.after, "roles") and \
            all(r in entry.changes.before.roles for r in removed) and \
            all(r in entry.changes.after.roles for r in added)
    return check


def guild_role_check(role):
    def check(entry):
        return role.id == entry.target.id  # getattr(entry.target, "id", None)
    return check


class ListenerEvents(LightningCog):
    """Cog that's meant to give us nicer events to use.

    Based off of Mousey's event system"""

    # TODO: A temp ignored cache.

    async def fetch_audit_log_entry(self, guild: discord.Guild, action: discord.AuditLogAction, *, target=None,
                                    limit: int = 50, check=None) -> Optional[discord.AuditLogEntry]:
        async for entry in guild.audit_logs(limit=limit, action=action):
            td = discord.utils.utcnow() - entry.created_at
            if td < timedelta(seconds=10):
                if target is not None and entry.target.id == target.id:
                    return entry

                if check is not None and check(entry):
                    return entry

    async def check_and_wait(self, guild: discord.Guild, *, timeout=0.5):
        """Checks if the bot has permissions to view the audit log and waits if the bot does have permission."""
        await self.bot.wait_until_ready()  # Might make this optional...

        if not guild.me:
            return False

        if not guild.me.guild_permissions.view_audit_log:
            # There's no point to wait if we don't have perms
            return False

        await asyncio.sleep(timeout)

    # Moderation Audit Log Integration Events
    @LightningCog.listener('on_member_remove')
    async def on_member_kick(self, member):
        check = await self.check_and_wait(member.guild)
        if check is False:
            return

        guild = member.guild

        entry = await self.fetch_audit_log_entry(guild, discord.AuditLogAction.kick, target=member)

        if not entry:  # The user was not kicked.
            return

        if member.joined_at is None or member.joined_at > entry.created_at:
            return

        if entry.user == self.bot.user:
            # Assuming it's already logged
            return

        event = AuditLogModAction("KICK", member, entry)
        self.bot.dispatch("lightning_member_kick", event)

    @LightningCog.listener()
    async def on_member_ban(self, guild, user):
        check = await self.check_and_wait(guild)
        if check is False:
            return

        entry = await self.fetch_audit_log_entry(guild, discord.AuditLogAction.ban, target=user)

        if not entry:
            return

        if entry.user == self.bot.user:
            # Assuming it's already logged
            return

        event = AuditLogModAction("BAN", user, entry, guild=guild)
        self.bot.dispatch("lightning_member_ban", event)

    @LightningCog.listener()
    async def on_member_unban(self, guild, user):
        check = await self.check_and_wait(guild)
        if check is False:
            return

        entry = await self.fetch_audit_log_entry(guild, discord.AuditLogAction.unban, target=user)

        if not entry:
            return

        if entry.user == self.bot.user:
            # Assuming it's already logged
            return

        event = AuditLogModAction("UNBAN", user, entry, guild=guild)
        self.bot.dispatch("lightning_member_unban", event)

    # Member events with optional audit log information
    @LightningCog.listener('on_member_update')
    async def on_member_nick_change(self, before, after):
        if before.nick == after.nick:
            return

        await self.check_and_wait(before.guild)  # We don't care if the check failed, thus no guard

        entry = await self.fetch_audit_log_entry(before.guild, discord.AuditLogAction.member_update, target=after,
                                                 check=match_attribute("nick", before.nick, after.nick))

        self.bot.dispatch("lightning_member_nick_change", MemberUpdateEvent(before, after, entry))

    @LightningCog.listener('on_member_update')
    async def on_member_role_change(self, before, after):
        if before.roles == after.roles:
            return

        await self.check_and_wait(before.guild)  # No guard needed

        entry = await self.fetch_audit_log_entry(before.guild, discord.AuditLogAction.member_role_update,
                                                 target=before, check=role_check(before, after))

        self.bot.dispatch("lightning_member_role_change", MemberRolesUpdateEvent(before, after, entry))

    # Member events that don't need audit logs
    @LightningCog.listener('on_member_update')
    async def on_member_passed_screening(self, before, after):
        if before.pending is True and after.pending is False:
            self.bot.dispatch("lightning_member_passed_screening", after)

    # Guild events with Audit Log Integration
    @LightningCog.listener()
    async def on_guild_role_delete(self, role):
        await self.check_and_wait(role.guild)

        entry = await self.fetch_audit_log_entry(role.guild, discord.AuditLogAction.role_delete,
                                                 target=role, check=guild_role_check(role))

        self.bot.dispatch("lightning_guild_role_delete", GuildRoleDeleteEvent(role, entry))

    # Dispatches role_add and role_remove events.
    @LightningCog.listener()
    async def on_lightning_member_role_change(self, event):
        for role in event.added_roles:
            self.bot.dispatch("lightning_member_role_add", MemberRoleUpdateEvent(role, event.entry))

        for role in event.removed_roles:
            self.bot.dispatch("lightning_member_role_remove", MemberRoleUpdateEvent(role, event.entry))


def setup(bot: LightningBot) -> None:
    bot.add_cog(ListenerEvents(bot))
