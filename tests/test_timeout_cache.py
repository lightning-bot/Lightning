from datetime import datetime, timedelta, timezone

from lightning.cogs.modlog.timeouts import TimeoutStateCache


def future(**kw):
    return datetime.now(timezone.utc) + timedelta(**kw)


def test_set_get_clear():
    c = TimeoutStateCache()
    c.set(1, 2, future(hours=1), moderator_id=3, reason="x")
    assert c.is_active(1, 2)
    assert c.get(1, 2).moderator_id == 3
    assert c.clear(1, 2) is not None
    assert not c.is_active(1, 2)


def test_extend_overwrites():
    c = TimeoutStateCache()
    c.set(1, 2, future(hours=1))
    new = future(hours=5)
    c.set(1, 2, new)
    assert c.get(1, 2).timed_out_until == new


def test_expired_not_active():
    c = TimeoutStateCache()
    c.set(1, 2, future(seconds=-1))
    assert c.get(1, 2) is None


def test_purge_and_guild_isolation():
    c = TimeoutStateCache()
    c.set(1, 2, future(seconds=-1))
    c.set(1, 3, future(hours=1))
    c.set(2, 2, future(hours=1))
    assert [(g, u) for g, u, _ in c.purge_expired()] == [(1, 2)]
    assert c.is_active(1, 3) and c.is_active(2, 2)
    c.clear_guild(1)
    assert not c.is_active(1, 3) and c.is_active(2, 2)


def test_get_and_is_active_do_not_evict_expired():
    c = TimeoutStateCache()
    state = c.set(1, 2, future(seconds=-1))
    assert c.get(1, 2) is None
    assert not c.is_active(1, 2)
    assert c.purge_expired() == [(1, 2, state)]


def test_purge_does_not_return_entry_twice():
    c = TimeoutStateCache()
    c.set(1, 2, future(seconds=-1))
    assert len(c.purge_expired()) == 1
    assert c.purge_expired() == []


def test_peek_sees_expired_and_remove_checks_identity():
    c = TimeoutStateCache()
    old = c.set(1, 2, future(seconds=-1))
    assert c.peek(1, 2) is old
    replacement = c.set(1, 2, future(hours=1))
    assert not c.remove(1, 2, old)
    assert c.peek(1, 2) is replacement
    assert c.remove(1, 2, replacement)
    assert c.peek(1, 2) is None


def test_peek_expired_does_not_remove():
    c = TimeoutStateCache()
    state = c.set(1, 2, future(seconds=-1))
    c.set(1, 3, future(hours=1))
    assert c.peek_expired() == [(1, 2, state)]
    assert c.peek_expired() == [(1, 2, state)]
