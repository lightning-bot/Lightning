import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from lightning.cogs.modlog.timeouts import (DEADLINE_TOLERANCE, TimeoutStateCache,
                                            TimeoutTracker)

GUILD, USER = 1, 2


def now():
    return datetime.now(timezone.utc)


async def settle():
    """Lets every runnable task run until it blocks, without waiting on the clock"""
    for _ in range(10):
        await asyncio.sleep(0)


class FakeStore:
    """An in-memory infractions table that follows the contract of the Postgres store.

    A method can be gated: it reports that it was entered, then waits to be released."""
    def __init__(self):
        self.rows = {}
        self.next_id = 1
        self.gates = {}
        self.entered = {}
        self.failures = {}

    def add(self, expiry, *, active=True, user_id=USER):
        row_id = self.next_id
        self.next_id += 1
        self.rows[row_id] = {"guild": GUILD, "user": user_id, "expiry": expiry, "active": active}
        return row_id

    def gate(self, name):
        self.gates[name] = asyncio.Event()
        self.entered[name] = asyncio.Event()

    def release(self, name):
        self.gates[name].set()

    async def _hook(self, name):
        if name in self.entered:
            self.entered[name].set()
            await self.gates[name].wait()
        if self.failures.get(name):
            raise RuntimeError(f"{name} failed")

    async def find_infraction(self, guild_id, user_id, earliest, latest, *, only_active):
        await self._hook("find_infraction")
        for row_id in sorted(self.rows, reverse=True):
            row = self.rows[row_id]
            if (row["guild"], row["user"]) == (guild_id, user_id) and earliest <= row["expiry"] <= latest \
                    and (row["active"] or not only_active):
                return row_id
        return None

    async def infraction_expiry(self, infraction_id):
        return self.rows[infraction_id]["expiry"]

    async def set_expiry(self, infraction_id, expiry):
        await self._hook("set_expiry")
        self.rows[infraction_id].update(expiry=expiry, active=True)

    async def deactivate(self, infraction_id, latest_expiry):
        await self._hook("deactivate")
        row = self.rows[infraction_id]
        if row["active"] and row["expiry"] <= latest_expiry:
            row["active"] = False
            return True
        return False

    async def deactivate_stale(self, guild_ids, at, exclude):
        await self._hook("deactivate_stale")
        for row in self.rows.values():
            if row["guild"] in guild_ids and row["active"] and row["expiry"] < at \
                    and (row["guild"], row["user"]) not in exclude:
                row["active"] = False


class TimeoutTrackingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = TimeoutStateCache()
        self.lock = asyncio.Lock()
        self.store = FakeStore()
        self.tracker = TimeoutTracker(self.cache, self.lock, self.store)

    def track(self, deadline, *, infraction_id=None):
        return self.cache.set(GUILD, USER, deadline, infraction_id=infraction_id)

    async def test_lookup_before_expiry_does_not_lose_the_entry(self):
        deadline = now() - timedelta(seconds=30)
        infraction = self.store.add(deadline)
        state = self.track(deadline, infraction_id=infraction)

        self.assertIsNone(self.cache.get(GUILD, USER))
        self.assertFalse(self.cache.is_active(GUILD, USER))

        self.assertEqual(await self.tracker.process_expired(), [(GUILD, USER, state)])
        self.assertFalse(self.store.rows[infraction]["active"])
        self.assertEqual(await self.tracker.process_expired(), [])

    async def test_extension_before_expiry_processing(self):
        old, new = now() - timedelta(seconds=1), now() + timedelta(hours=1)
        infraction = self.store.add(old)
        self.track(old, infraction_id=infraction)

        await self.tracker.apply_change(GUILD, USER, old, new)
        self.assertEqual(await self.tracker.process_expired(), [])

        self.assertTrue(self.store.rows[infraction]["active"])
        self.assertEqual(self.store.rows[infraction]["expiry"], new)
        self.assertEqual(self.cache.get(GUILD, USER).timed_out_until, new)

    async def test_expiry_processing_before_extension(self):
        old, new = now() - timedelta(seconds=1), now() + timedelta(hours=1)
        infraction = self.store.add(old)
        self.track(old, infraction_id=infraction)
        self.store.gate("deactivate")

        expiry = asyncio.create_task(self.tracker.process_expired())
        await self.store.entered["deactivate"].wait()
        extension = asyncio.create_task(self.tracker.apply_change(GUILD, USER, old, new))
        await settle()
        self.assertFalse(extension.done())  # The extension has to wait for the transition in progress

        self.store.release("deactivate")
        self.assertEqual(len(await expiry), 1)
        await extension

        # Expiry got there first, the extension then brought the same infraction back with the new deadline
        self.assertTrue(self.store.rows[infraction]["active"])
        self.assertEqual(self.store.rows[infraction]["expiry"], new)
        state = self.cache.get(GUILD, USER)
        self.assertEqual((state.timed_out_until, state.infraction_id), (new, infraction))

    async def test_removal_before_expiry_processing(self):
        deadline = now() - timedelta(seconds=1)
        infraction = self.store.add(deadline)
        self.track(deadline, infraction_id=infraction)

        await self.tracker.apply_removal(GUILD, USER, deadline)
        self.assertEqual(await self.tracker.process_expired(), [])
        self.assertFalse(self.store.rows[infraction]["active"])
        self.assertIsNone(self.cache.peek(GUILD, USER))

    async def test_removal_racing_expiry_processing(self):
        deadline = now() - timedelta(seconds=1)
        infraction = self.store.add(deadline)
        self.track(deadline, infraction_id=infraction)
        self.store.gate("deactivate")

        expiry = asyncio.create_task(self.tracker.process_expired())
        await self.store.entered["deactivate"].wait()
        removal = asyncio.create_task(self.tracker.apply_removal(GUILD, USER, deadline))
        await settle()
        self.assertFalse(removal.done())

        self.store.release("deactivate")
        self.assertEqual(len(await expiry), 1)
        await removal

        self.assertFalse(self.store.rows[infraction]["active"])
        self.assertIsNone(self.cache.peek(GUILD, USER))

    async def test_stale_expiry_after_replacement(self):
        old, new = now() - timedelta(seconds=1), now() + timedelta(hours=1)
        infraction = self.store.add(old)
        self.track(old, infraction_id=infraction)
        self.store.gate("deactivate")

        expiry = asyncio.create_task(self.tracker.process_expired())
        await self.store.entered["deactivate"].wait()
        # Something replaced the timeout behind the lock's back while the expiry was in flight
        self.store.rows[infraction]["expiry"] = new
        replacement = self.track(new, infraction_id=infraction)
        self.store.release("deactivate")

        self.assertEqual(await expiry, [])
        self.assertIs(self.cache.peek(GUILD, USER), replacement)
        self.assertTrue(self.store.rows[infraction]["active"])

    async def test_expiry_does_not_touch_an_extended_infraction(self):
        old, new = now() - timedelta(seconds=1), now() + timedelta(hours=1)
        infraction = self.store.add(new)
        self.track(old, infraction_id=infraction)

        await self.tracker.process_expired()
        self.assertTrue(self.store.rows[infraction]["active"])

    async def test_database_failure_is_retried(self):
        deadline = now() - timedelta(seconds=1)
        infraction = self.store.add(deadline)
        state = self.track(deadline, infraction_id=infraction)
        self.store.failures["deactivate"] = True

        with self.assertLogs("lightning.cogs.modlog.timeouts", level="ERROR"):
            self.assertEqual(await self.tracker.process_expired(), [])
        self.assertIs(self.cache.peek(GUILD, USER), state)
        self.assertTrue(self.store.rows[infraction]["active"])
        self.assertFalse(self.lock.locked())

        self.store.failures["deactivate"] = False
        self.assertEqual(await self.tracker.process_expired(), [(GUILD, USER, state)])
        self.assertFalse(self.store.rows[infraction]["active"])

    async def test_one_failure_does_not_block_other_entries(self):
        deadline = now() - timedelta(seconds=1)
        self.store.add(deadline, user_id=3)
        good = self.store.add(deadline)
        self.cache.set(GUILD, 3, deadline, infraction_id=1)
        self.track(deadline, infraction_id=good)

        original = self.store.deactivate

        async def flaky(infraction_id, latest):
            if infraction_id == 1:
                raise RuntimeError("boom")
            return await original(infraction_id, latest)

        self.store.deactivate = flaky
        with self.assertLogs("lightning.cogs.modlog.timeouts", level="ERROR"):
            done = await self.tracker.process_expired()

        self.assertEqual([u for _, u, _ in done], [USER])
        self.assertIsNotNone(self.cache.peek(GUILD, 3))

    async def test_infraction_found_by_deadline_when_not_linked(self):
        deadline = now() - timedelta(seconds=1)
        infraction = self.store.add(deadline + DEADLINE_TOLERANCE / 2)
        unrelated = self.store.add(deadline - timedelta(hours=1))  # An older timeout for the same member
        self.track(deadline)

        await self.tracker.process_expired()
        self.assertFalse(self.store.rows[infraction]["active"])
        self.assertTrue(self.store.rows[unrelated]["active"])

    async def test_new_timeout_links_to_existing_infraction(self):
        deadline = now() + timedelta(hours=1)
        infraction = self.store.add(deadline)
        await self.tracker.apply_change(GUILD, USER, None, deadline, moderator_id=5, reason="r")
        state = self.cache.get(GUILD, USER)
        self.assertEqual((state.infraction_id, state.moderator_id, state.reason), (infraction, 5, "r"))

    async def test_infraction_logged_after_timeout_is_linked(self):
        deadline = now() + timedelta(hours=1)
        await self.tracker.apply_change(GUILD, USER, None, deadline)
        self.assertIsNone(self.cache.get(GUILD, USER).infraction_id)

        infraction = self.store.add(deadline)
        self.assertTrue(await self.tracker.link_infraction(GUILD, USER, infraction))
        self.assertEqual(self.cache.get(GUILD, USER).infraction_id, infraction)

    async def test_link_ignores_an_infraction_for_another_deadline(self):
        await self.tracker.apply_change(GUILD, USER, None, now() + timedelta(hours=1))
        other = self.store.add(now() + timedelta(days=2))
        self.assertFalse(await self.tracker.link_infraction(GUILD, USER, other))

    async def test_stale_removal_is_ignored(self):
        current = now() + timedelta(hours=1)
        infraction = self.store.add(current)
        self.track(current, infraction_id=infraction)

        await self.tracker.apply_removal(GUILD, USER, now() + timedelta(minutes=5))
        self.assertTrue(self.store.rows[infraction]["active"])
        self.assertIsNotNone(self.cache.get(GUILD, USER))

    async def test_reconcile_backfills_and_skips_members_still_timed_out(self):
        gone = self.store.add(now() - timedelta(hours=1), user_id=3)
        still = self.store.add(now() - timedelta(hours=1))  # Extended while the bot was down
        await self.tracker.reconcile([(GUILD, USER, now() + timedelta(hours=1)), (GUILD, 9, None)], [GUILD])

        self.assertIsNotNone(self.cache.get(GUILD, USER))
        self.assertIsNone(self.cache.peek(GUILD, 9))
        self.assertFalse(self.store.rows[gone]["active"])
        self.assertTrue(self.store.rows[still]["active"])

    async def test_backfill_does_not_replace_an_unprocessed_expired_state(self):
        state = self.track(now() - timedelta(seconds=1))
        await self.tracker.reconcile([(GUILD, USER, now() + timedelta(hours=1))], [])
        self.assertIs(self.cache.peek(GUILD, USER), state)

    async def test_cleanup_waits_for_the_transition_in_progress(self):
        deadline = now() - timedelta(seconds=1)
        infraction = self.store.add(deadline)
        self.track(deadline, infraction_id=infraction)
        self.store.gate("deactivate")

        expiry = asyncio.create_task(self.tracker.process_expired())
        await self.store.entered["deactivate"].wait()
        cleanup = asyncio.create_task(self.tracker.forget_guild(GUILD))
        await settle()
        self.assertFalse(cleanup.done())

        self.store.release("deactivate")
        self.assertEqual(len(await expiry), 1)  # The entry wasn't pulled out from under the expiry
        await cleanup

    async def test_forget_member_keeps_expired_state_for_processing(self):
        self.track(now() - timedelta(seconds=1))
        self.cache.set(GUILD, 3, now() + timedelta(hours=1))
        await self.tracker.forget_member(GUILD, USER)
        await self.tracker.forget_member(GUILD, 3)
        self.assertIsNotNone(self.cache.peek(GUILD, USER))
        self.assertIsNone(self.cache.peek(GUILD, 3))


if __name__ == "__main__":
    unittest.main()
