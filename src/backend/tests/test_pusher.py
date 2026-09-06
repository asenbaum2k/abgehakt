"""Tests for the pusher daemon logic (no ntfy server needed)."""
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pusher  # noqa: E402

BERLIN = ZoneInfo("Europe/Berlin")


def make_todo(**overrides):
    base = {
        "id": "t1",
        "title": "Milch kaufen",
        "notes": "",
        "due_date": "2026-09-07",
        "due_time": "18:30",
        "notify_at": "due",
        "notified_at": "",
        "completed": 0,
    }
    base.update(overrides)
    return base


# ── compute_notify_dt ───────────────────────────────────────


def test_notify_dt_exact_due():
    todo = make_todo()
    dt = pusher.compute_notify_dt(todo, tz=BERLIN)
    assert dt == datetime(2026, 9, 7, 18, 30, tzinfo=BERLIN)


def test_notify_dt_5min_before():
    todo = make_todo(notify_at="5min_before")
    dt = pusher.compute_notify_dt(todo, tz=BERLIN)
    assert dt == datetime(2026, 9, 7, 18, 25, tzinfo=BERLIN)


def test_notify_dt_1h_before():
    todo = make_todo(notify_at="1h_before")
    dt = pusher.compute_notify_dt(todo, tz=BERLIN)
    assert dt == datetime(2026, 9, 7, 17, 30, tzinfo=BERLIN)


def test_notify_dt_none_without_notify_at():
    assert pusher.compute_notify_dt(make_todo(notify_at="")) is None


def test_notify_dt_none_without_due_date():
    assert pusher.compute_notify_dt(make_todo(due_date="")) is None


def test_notify_dt_none_without_due_time():
    assert pusher.compute_notify_dt(make_todo(due_time="")) is None


def test_notify_dt_none_unknown_offset():
    assert pusher.compute_notify_dt(make_todo(notify_at="weekly")) is None


def test_notify_dt_none_bad_date():
    assert pusher.compute_notify_dt(make_todo(due_date="07.09.2026")) is None


# ── timezone handling (the classic bug) ─────────────────────


def test_berlin_wallclock_maps_to_correct_utc():
    """18:30 Berlin (CEST, UTC+2 in Sept) must be 16:30 UTC."""
    dt = pusher.compute_notify_dt(make_todo(), tz=BERLIN)
    assert dt.astimezone(ZoneInfo("UTC")).hour == 16
    assert dt.utcoffset() == timedelta(hours=2)  # CEST in September


def test_winter_offset_is_plus_1():
    todo = make_todo(due_date="2026-01-15", due_time="12:00")
    dt = pusher.compute_notify_dt(todo, tz=BERLIN)
    assert dt.utcoffset() == timedelta(hours=1)  # CET


# ── due_for_notification ────────────────────────────────────


def test_due_now_sends():
    todo = make_todo()
    now = datetime(2026, 9, 7, 18, 30, 30, tzinfo=BERLIN)
    assert pusher.due_for_notification(todo, now, timedelta(minutes=180)) == "send"


def test_future_waits():
    todo = make_todo()
    now = datetime(2026, 9, 7, 18, 29, tzinfo=BERLIN)
    assert pusher.due_for_notification(todo, now, timedelta(minutes=180)) == "wait"


def test_too_old_skips():
    todo = make_todo()
    now = datetime(2026, 9, 7, 22, 0, tzinfo=BERLIN)  # 3.5h later
    assert pusher.due_for_notification(todo, now, timedelta(minutes=180)) == "skip_late"


def test_within_grace_still_sends():
    todo = make_todo()
    now = datetime(2026, 9, 7, 19, 0, tzinfo=BERLIN)  # 30min late
    assert pusher.due_for_notification(todo, now, timedelta(minutes=180)) == "send"


# ── is_notifiable ───────────────────────────────────────────


def test_completed_is_not_notifiable():
    assert pusher.is_notifiable(make_todo(completed=1)) is False


def test_already_notified_is_not_notifiable():
    todo = make_todo(notified_at="2026-09-07T16:30:01+00:00")
    assert pusher.is_notifiable(todo) is False


def test_open_unnotified_is_notifiable():
    assert pusher.is_notifiable(make_todo()) is True
