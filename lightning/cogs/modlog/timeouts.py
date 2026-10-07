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
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TimeoutState:
    timed_out_until: datetime
    moderator_id: Optional[int] = None
    reason: Optional[str] = None
    infraction_id: Optional[int] = None


class TimeoutStateCache:
    """In-memory cache of active member timeouts, bucketed by guild."""

    def __init__(self):
        self._guilds: dict[int, dict[int, TimeoutState]] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def set(self, guild_id: int, user_id: int, timed_out_until: datetime, *, moderator_id: Optional[int] = None,
            reason: Optional[str] = None, infraction_id: Optional[int] = None) -> TimeoutState:
        state = TimeoutState(timed_out_until, moderator_id, reason, infraction_id)
        self._guilds.setdefault(guild_id, {})[user_id] = state
        return state

    def get(self, guild_id: int, user_id: int) -> Optional[TimeoutState]:
        """Returns the state if it's still active.

        Expired states are not returned, but they stay stored until purge_expired() hands them over."""
        bucket = self._guilds.get(guild_id)
        state = bucket.get(user_id) if bucket else None
        if state is None or state.timed_out_until <= self._now():
            return None
        return state

    def is_active(self, guild_id: int, user_id: int) -> bool:
        return self.get(guild_id, user_id) is not None

    def clear(self, guild_id: int, user_id: int) -> Optional[TimeoutState]:
        bucket = self._guilds.get(guild_id)
        if bucket is None:
            return None
        state = bucket.pop(user_id, None)
        if not bucket:
            del self._guilds[guild_id]
        return state

    def clear_guild(self, guild_id: int) -> None:
        self._guilds.pop(guild_id, None)

    def purge_expired(self) -> list[tuple[int, int, TimeoutState]]:
        """Removes expired entries and returns them as (guild_id, user_id, state)"""
        now = self._now()
        expired = [(g, u, st) for g, bucket in self._guilds.items() for u, st in bucket.items()
                   if st.timed_out_until <= now]
        for g, u, _ in expired:
            self.clear(g, u)
        return expired
