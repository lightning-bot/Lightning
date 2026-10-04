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

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Union

import discord

from lightning.enums import ActionType, AutoModPunishmentType
from lightning.events import LightningAutoModInfractionEvent
from lightning.utils.time import natural_timedelta

if TYPE_CHECKING:
    from lightning import LightningBot


@dataclass
class PunishmentContext:
    """Everything a punishment needs to run.

    ``moderator`` is whoever is responsible for the action. AutoMod uses the bot, while
    message reports use the moderator that confirmed the action.
    """
    bot: LightningBot
    message: discord.Message
    reason: str
    moderator: Union[discord.Member, discord.User, discord.ClientUser]
    duration: Optional[Union[int, datetime.datetime]] = None
    content: Optional[str] = None

    @property
    def member(self) -> discord.Member:
        return self.message.author  # type: ignore

    @property
    def guild(self) -> discord.Guild:
        return self.message.guild  # type: ignore

    @property
    def expiry(self) -> Optional[datetime.datetime]:
        if self.duration is None:
            return None
        if isinstance(self.duration, datetime.datetime):
            return self.duration
        return self.message.created_at + datetime.timedelta(seconds=self.duration)

    @property
    def audit_reason(self) -> str:
        # Moderators aren't the bot, so make it clear in the audit log who is responsible.
        if self.moderator.id == self.bot.user.id:  # type: ignore
            return self.reason[:512]
        return f"{self.moderator} ({self.moderator.id}): {self.reason}"[:512]

    async def log(self, action: str, **kwargs: Any) -> None:
        """Records the infraction and dispatches the matching event."""
        timestamp = kwargs.pop("timestamp", None) or discord.utils.utcnow()
        event = LightningAutoModInfractionEvent.from_message(action, self.message, self.reason,
                                                             tracked_content=self.content,
                                                             moderator=self.moderator, **kwargs)
        await event.action.add_infraction(self.bot.pool)

        if event.action.expiry:
            event.action.expiry = natural_timedelta(event.action.expiry, source=timestamp)

        # Timed actions are still mutes/bans as far as event listeners are concerned
        base = {"TIMEMUTE": ActionType.MUTE, "TIMEBAN": ActionType.BAN}.get(action) or ActionType[action]
        self.bot.dispatch(f"lightning_member_{str(base).lower()}", event)

    async def add_timer(self, event: str, **kwargs: Any) -> Any:
        expiry = self.expiry
        cog = self.bot.get_cog("Reminders")
        return await cog.add_timer(event, self.message.created_at, expiry, guild_id=self.guild.id,  # type: ignore
                                   user_id=self.member.id, mod_id=self.moderator.id, force_insert=True,
                                   timezone=expiry.tzinfo or datetime.timezone.utc, **kwargs)  # type: ignore


class Punishment:
    """Base class for a punishment. Subclasses are registered with :func:`register`."""
    type: AutoModPunishmentType
    # Used for DM notifications
    verb: str = "punished"
    preposition: str = "in"
    takes_duration: bool = False

    async def apply(self, ctx: PunishmentContext) -> None:
        raise NotImplementedError


PUNISHMENTS: dict[AutoModPunishmentType, Punishment] = {}


def register(cls: type[Punishment]) -> type[Punishment]:
    PUNISHMENTS[cls.type] = cls()
    return cls


@register
class Delete(Punishment):
    type = AutoModPunishmentType.DELETE

    async def apply(self, ctx: PunishmentContext) -> None:
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


@register
class Warn(Punishment):
    type = AutoModPunishmentType.WARN
    verb = "warned"

    async def apply(self, ctx: PunishmentContext) -> None:
        await ctx.log("WARN")


@register
class Kick(Punishment):
    type = AutoModPunishmentType.KICK
    verb = "kicked"
    preposition = "from"

    async def apply(self, ctx: PunishmentContext) -> None:
        await ctx.member.kick(reason=ctx.audit_reason)
        await ctx.log("KICK")


@register
class Ban(Punishment):
    type = AutoModPunishmentType.BAN
    verb = "banned"
    preposition = "from"
    takes_duration = True

    async def apply(self, ctx: PunishmentContext) -> None:
        await ctx.member.ban(reason=ctx.audit_reason)
        if ctx.duration:
            await self._timed(ctx)
        else:
            await ctx.log("BAN")

    async def _timed(self, ctx: PunishmentContext) -> None:
        timer_id = await ctx.add_timer("timeban")
        await ctx.log("TIMEBAN", expiry=ctx.expiry, timer_id=timer_id)


@register
class Mute(Punishment):
    type = AutoModPunishmentType.MUTE
    verb = "muted"
    takes_duration = True

    async def apply(self, ctx: PunishmentContext) -> None:
        if ctx.duration:
            await self._timed(ctx)
        else:
            await self._permanent(ctx)

    async def _get_role(self, ctx: PunishmentContext) -> Optional[discord.Role]:
        cfg = await ctx.bot.get_cog("Moderation").get_mod_config(ctx.guild.id)  # type: ignore
        if not cfg or not cfg.mute_role_id:
            return None
        return ctx.guild.get_role(cfg.mute_role_id)

    def _can_timeout(self, ctx: PunishmentContext, expiry: datetime.datetime) -> bool:
        me = ctx.guild.me
        return bool(ctx.message.channel.permissions_for(me).moderate_members
                    and expiry <= ctx.message.created_at + datetime.timedelta(days=28))

    async def _add_role(self, ctx: PunishmentContext, role: discord.Role) -> None:
        await ctx.member.add_roles(role, reason=ctx.audit_reason)
        await ctx.bot.get_cog("Moderation").add_punishment_role(ctx.guild.id, ctx.member.id, role.id)  # type: ignore

    async def _permanent(self, ctx: PunishmentContext) -> None:
        if not ctx.message.channel.permissions_for(ctx.guild.me).manage_roles:
            return

        role = await self._get_role(ctx)
        if not role:
            return

        await self._add_role(ctx, role)
        await ctx.log("MUTE", timestamp=ctx.message.created_at)

    async def _timed(self, ctx: PunishmentContext) -> None:
        expiry = ctx.expiry
        if self._can_timeout(ctx, expiry):  # type: ignore
            await ctx.member.edit(timed_out_until=expiry, reason=ctx.audit_reason)
            return

        role = await self._get_role(ctx)
        if not role or not ctx.message.channel.permissions_for(ctx.guild.me).manage_roles:
            return

        job_id = await ctx.add_timer("timemute", role_id=role.id)
        await self._add_role(ctx, role)
        await ctx.log("TIMEMUTE", expiry=expiry, timer_id=job_id, timestamp=ctx.message.created_at)


async def apply_punishment(bot: LightningBot, punishment: Union[AutoModPunishmentType, str], message: discord.Message,
                           *, reason: str, moderator: Optional[Union[discord.Member, discord.User]] = None,
                           duration: Optional[Union[int, datetime.datetime]] = None,
                           content: Optional[str] = None) -> None:
    """Applies a punishment to the author of a message.

    ``moderator`` defaults to the bot, which is what AutoMod wants.
    """
    if not isinstance(punishment, AutoModPunishmentType):
        punishment = AutoModPunishmentType[str(punishment).upper()]

    ctx = PunishmentContext(bot, message, reason, moderator or message.guild.me,  # type: ignore
                            duration=duration, content=content)
    await PUNISHMENTS[punishment].apply(ctx)
