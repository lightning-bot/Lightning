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

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Iterator, Optional, Protocol

log = logging.getLogger(__name__)

# Discord and the infractions table can disagree on a deadline by a hair (rounding, clock skew between
# when we computed the expiry and when Discord stored it), so deadlines are matched within this window.
DEADLINE_TOLERANCE = timedelta(seconds=2)


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

    def peek(self, guild_id: int, user_id: int) -> Optional[TimeoutState]:
        """Returns the stored state whether or not it has expired"""
        bucket = self._guilds.get(guild_id)
        return bucket.get(user_id) if bucket else None

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

    def remove(self, guild_id: int, user_id: int, expected: TimeoutState) -> bool:
        """Removes the entry only if it is still the exact state the caller was working on"""
        if self.peek(guild_id, user_id) is not expected:
            return False
        self.clear(guild_id, user_id)
        return True

    def clear_guild(self, guild_id: int) -> None:
        self._guilds.pop(guild_id, None)

    def states(self) -> Iterator[tuple[int, int, TimeoutState]]:
        """Iterates over a snapshot of every stored state as (guild_id, user_id, state)"""
        return iter([(g, u, st) for g, bucket in self._guilds.items() for u, st in bucket.items()])

    def peek_expired(self) -> list[tuple[int, int, TimeoutState]]:
        """Lists expired entries as (guild_id, user_id, state) without removing them"""
        now = self._now()
        return [(g, u, st) for g, u, st in self.states() if st.timed_out_until <= now]

    def purge_expired(self) -> list[tuple[int, int, TimeoutState]]:
        """Removes expired entries and returns them as (guild_id, user_id, state)"""
        expired = self.peek_expired()
        for g, u, _ in expired:
            self.clear(g, u)
        return expired


class TimeoutStore(Protocol):
    """The infraction operations that timeout tracking needs"""
    async def find_infraction(self, guild_id: int, user_id: int, earliest: datetime, latest: datetime, *,
                              only_active: bool) -> Optional[int]: ...

    async def infraction_expiry(self, infraction_id: int) -> Optional[datetime]: ...

    async def set_expiry(self, infraction_id: int, expiry: datetime) -> None: ...

    async def deactivate(self, infraction_id: int, latest_expiry: datetime) -> bool: ...

    async def deactivate_stale(self, guild_ids: list[int], now: datetime,
                               exclude: list[tuple[int, int]]) -> None: ...


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    return dt.replace(tzinfo=timezone.utc) if dt is not None else None


class PostgresTimeoutStore:
    """Every statement targets one infraction by ID, except the startup sweep, which only touches
    infractions whose recorded expiry has already passed."""
    def __init__(self, get_pool: Callable[[], object]) -> None:
        self._get_pool = get_pool

    async def find_infraction(self, guild_id, user_id, earliest, latest, *, only_active):
        query = """SELECT id FROM infractions
                   WHERE action=10 AND guild_id=$1 AND user_id=$2 AND expiry BETWEEN $3 AND $4
                   AND (NOT $5::boolean OR active IS TRUE)
                   ORDER BY id DESC LIMIT 1;"""
        return await self._get_pool().fetchval(query, guild_id, user_id, _naive_utc(earliest),
                                               _naive_utc(latest), only_active)

    async def infraction_expiry(self, infraction_id):
        query = "SELECT expiry FROM infractions WHERE id=$1 AND action=10;"
        return _aware_utc(await self._get_pool().fetchval(query, infraction_id))

    async def set_expiry(self, infraction_id, expiry):
        query = "UPDATE infractions SET expiry=$2, active='t' WHERE id=$1 AND action=10;"
        await self._get_pool().execute(query, infraction_id, _naive_utc(expiry))

    async def deactivate(self, infraction_id, latest_expiry):
        query = """UPDATE infractions SET active='f'
                   WHERE id=$1 AND action=10 AND active IS TRUE AND expiry <= $2
                   RETURNING id;"""
        return await self._get_pool().fetchval(query, infraction_id, _naive_utc(latest_expiry)) is not None

    async def deactivate_stale(self, guild_ids, now, exclude):
        query = """UPDATE infractions SET active='f'
                   WHERE action=10 AND active IS TRUE AND guild_id=ANY($1::bigint[]) AND expiry < $2
                   AND (guild_id, user_id) NOT IN (SELECT * FROM unnest($3::bigint[], $4::bigint[]));"""
        await self._get_pool().execute(query, guild_ids, _naive_utc(now), [g for g, _ in exclude],
                                       [u for _, u in exclude])


class TimeoutTracker:
    """Coordinates the timeout cache with the infractions table.

    The lock is owned by whoever builds the tracker (ModLog) and is shared by every conflicting transition:
    changes, removals, expiry and startup reconciliation. It is held across the database call and the cache
    mutation that goes with it. Anything that has to be announced is returned so the caller can dispatch it
    after the lock is released."""

    def __init__(self, cache: TimeoutStateCache, lock: asyncio.Lock, store: TimeoutStore) -> None:
        self.cache = cache
        self.lock = lock
        self.store = store

    @staticmethod
    def _close(a: datetime, b: datetime) -> bool:
        return abs(a - b) <= DEADLINE_TOLERANCE

    async def _find(self, guild_id: int, user_id: int, deadline: datetime, *, only_active: bool) -> Optional[int]:
        try:
            return await self.store.find_infraction(guild_id, user_id, deadline - DEADLINE_TOLERANCE,
                                                    deadline + DEADLINE_TOLERANCE, only_active=only_active)
        except Exception:
            log.exception("Unable to look up the infraction for a timeout (guild %s, user %s)", guild_id, user_id)
            return None

    async def _deactivate(self, guild_id: int, user_id: int, infraction_id: Optional[int],
                          deadline: datetime) -> None:
        """Deactivates the infraction that belongs to a timeout that ended at the deadline. Raises on failure."""
        if infraction_id is None:
            infraction_id = await self.store.find_infraction(guild_id, user_id, deadline - DEADLINE_TOLERANCE,
                                                             deadline + DEADLINE_TOLERANCE, only_active=True)
        if infraction_id is not None:
            # An infraction that now expires later than this deadline belongs to an extended timeout, so
            # the store leaves it alone.
            await self.store.deactivate(infraction_id, deadline + DEADLINE_TOLERANCE)

    async def apply_change(self, guild_id: int, user_id: int, before: Optional[datetime],
                           after: Optional[datetime], *, moderator_id: Optional[int] = None,
                           reason: Optional[str] = None) -> None:
        """Applies a change in a member's timeout deadline as reported by Discord"""
        async with self.lock:
            if after is None or after <= self.cache._now():
                await self._remove(guild_id, user_id, before)
                return

            state = self.cache.peek(guild_id, user_id)
            infraction_id = state.infraction_id if state else None

            if before is not None and not self._close(before, after):
                # Extended or shortened. This also revives the infraction if expiry processing got to it first.
                if infraction_id is None:
                    infraction_id = await self._find(guild_id, user_id, before, only_active=False)
                if infraction_id is not None:
                    try:
                        await self.store.set_expiry(infraction_id, after)
                    except Exception:
                        log.exception("Unable to update infraction %s to the new timeout deadline", infraction_id)
            elif infraction_id is None:
                infraction_id = await self._find(guild_id, user_id, after, only_active=True)

            self.cache.set(guild_id, user_id, after,
                           moderator_id=moderator_id if moderator_id is not None else
                           (state.moderator_id if state else None),
                           reason=reason if reason is not None else (state.reason if state else None),
                           infraction_id=infraction_id)

    async def apply_removal(self, guild_id: int, user_id: int, expected_deadline: Optional[datetime]) -> None:
        """Handles a timeout that was removed early"""
        async with self.lock:
            await self._remove(guild_id, user_id, expected_deadline)

    async def _remove(self, guild_id: int, user_id: int, expected_deadline: Optional[datetime]) -> None:
        state = self.cache.peek(guild_id, user_id)
        if state is not None and expected_deadline is not None and not self._close(state.timed_out_until,
                                                                                    expected_deadline):
            return  # The removal is about a timeout that has already been replaced

        deadline = state.timed_out_until if state is not None else expected_deadline
        if deadline is not None:
            await self._deactivate(guild_id, user_id, state.infraction_id if state else None, deadline)

        if state is not None:
            self.cache.remove(guild_id, user_id, state)

    async def link_infraction(self, guild_id: int, user_id: int, infraction_id: int) -> bool:
        """Attaches a freshly logged timeout infraction to the tracked state it describes"""
        async with self.lock:
            state = self.cache.peek(guild_id, user_id)
            if state is None or state.infraction_id is not None:
                return False

            try:
                expiry = await self.store.infraction_expiry(infraction_id)
            except Exception:
                log.exception("Unable to read infraction %s to link it to a timeout", infraction_id)
                return False

            if expiry is None or not self._close(expiry, state.timed_out_until):
                return False

            self.cache.set(guild_id, user_id, state.timed_out_until, moderator_id=state.moderator_id,
                           reason=state.reason, infraction_id=infraction_id)
            return True

    async def process_expired(self) -> list[tuple[int, int, TimeoutState]]:
        """Deactivates the infractions of expired timeouts and forgets them.

        An entry is only removed once its database update succeeded, so a failure is retried on the next
        run. Returns the entries that were handled so that the caller can announce them."""
        done = []
        async with self.lock:
            for guild_id, user_id, state in self.cache.peek_expired():
                try:
                    await self._deactivate(guild_id, user_id, state.infraction_id, state.timed_out_until)
                except Exception:
                    log.exception("Unable to deactivate the expired timeout infraction (guild %s, user %s); "
                                  "it will be retried", guild_id, user_id)
                    continue

                if self.cache.remove(guild_id, user_id, state):
                    done.append((guild_id, user_id, state))
        return done

    async def reconcile(self, entries: Iterable[tuple[int, int, Optional[datetime]]],
                        guild_ids: list[int]) -> None:
        """Backfills timeouts Discord reports that we don't know about, then deactivates the infractions of
        timeouts that ran out while we weren't watching, other than for members who are still timed out."""
        async with self.lock:
            now = self.cache._now()
            for guild_id, user_id, until in entries:
                if until is not None and until > now and self.cache.peek(guild_id, user_id) is None:
                    self.cache.set(guild_id, user_id, until)

            if guild_ids:
                exclude = [(g, u) for g, u, st in self.cache.states() if st.timed_out_until > now]
                await self.store.deactivate_stale(guild_ids, now, exclude)

    async def forget_member(self, guild_id: int, user_id: int) -> None:
        """Drops a departed member's active timeout. Expired states stay so expiry processing still sees them."""
        async with self.lock:
            if self.cache.get(guild_id, user_id) is not None:
                self.cache.clear(guild_id, user_id)

    async def forget_guild(self, guild_id: int) -> None:
        async with self.lock:
            self.cache.clear_guild(guild_id)
