from datetime import datetime, timedelta, timezone

from lightning.cache import TimeoutStateCache


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
