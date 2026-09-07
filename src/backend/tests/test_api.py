"""
abgehakt v2 — Backend tests via FastAPI TestClient.
"""
import os
import sys
import uuid
import pytest

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app
from database import init_db, DB_PATH, get_all_tags

# Use a test DB so we don't trash the real one
TEST_DB = os.path.join(os.path.dirname(__file__), "..", "test_todos.db")


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """Override DB_PATH for tests and init fresh."""
    monkeypatch.setattr("database.DB_PATH", TEST_DB)
    monkeypatch.setattr("main.init_db", lambda: init_db())
    # Clean up old test DB
    for suffix in ["", "-shm", "-wal"]:
        path = TEST_DB + suffix
        if os.path.exists(path):
            os.remove(path)
    init_db()
    yield
    # Cleanup
    for suffix in ["", "-shm", "-wal"]:
        path = TEST_DB + suffix
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def client():
    return TestClient(app)


# ── Basic CRUD ────────────────────────────────────────────────


def test_create_todo(client):
    resp = client.post("/api/todos", json={"title": "Test Todo"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test Todo"
    assert data["completed"] is False
    assert "id" in data


def test_create_empty_title(client):
    resp = client.post("/api/todos", json={"title": ""})
    assert resp.status_code == 400


def test_list_todos(client):
    client.post("/api/todos", json={"title": "A"})
    client.post("/api/todos", json={"title": "B"})
    resp = client.get("/api/todos")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_get_todo(client):
    resp = client.post("/api/todos", json={"title": "Get Me"})
    tid = resp.json()["id"]
    resp = client.get(f"/api/todos/{tid}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get Me"


def test_get_nonexistent(client):
    resp = client.get("/api/todos/nonexistent")
    assert resp.status_code == 404


def test_update_todo(client):
    resp = client.post("/api/todos", json={"title": "Old"})
    tid = resp.json()["id"]
    resp = client.patch(f"/api/todos/{tid}", json={"title": "New"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New"


def test_patch_no_fields(client):
    resp = client.post("/api/todos", json={"title": "X"})
    tid = resp.json()["id"]
    resp = client.patch(f"/api/todos/{tid}", json={})
    assert resp.status_code == 400


def test_delete_todo(client):
    resp = client.post("/api/todos", json={"title": "Delete Me"})
    tid = resp.json()["id"]
    resp = client.delete(f"/api/todos/{tid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"]["id"] == tid

    # Should be gone
    resp = client.get(f"/api/todos/{tid}")
    assert resp.status_code == 404


# ── Tags ──────────────────────────────────────────────────────


def test_create_with_tags(client):
    resp = client.post("/api/todos", json={
        "title": "Tagged", "tags": "work,urgent"
    })
    assert resp.status_code == 201
    assert resp.json()["tags"] == "work,urgent"


def test_list_tags(client):
    client.post("/api/todos", json={"title": "A", "tags": "work,urgent"})
    client.post("/api/todos", json={"title": "B", "tags": "home,chores"})
    resp = client.get("/api/tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert "chores" in tags
    assert "home" in tags
    assert "urgent" in tags
    assert "work" in tags


def test_filter_by_tag(client):
    client.post("/api/todos", json={"title": "Work item", "tags": "work"})
    client.post("/api/todos", json={"title": "Home item", "tags": "home"})
    client.post("/api/todos", json={"title": "Both", "tags": "work,home"})

    resp = client.get("/api/todos?tag=work")
    data = resp.json()
    titles = {t["title"] for t in data}
    assert "Work item" in titles
    assert "Both" in titles
    assert "Home item" not in titles


def test_tag_index_removes_unused_tags(client):
    resp = client.post("/api/todos", json={"title": "Tagged", "tags": "temporary,keep"})
    tid = resp.json()["id"]
    client.patch(f"/api/todos/{tid}", json={"tags": "keep"})
    assert client.get("/api/tags").json() == ["keep"]
    client.delete(f"/api/todos/{tid}")
    assert client.get("/api/tags").json() == []


# ── Recurring ─────────────────────────────────────────────────


def test_create_recurring(client):
    resp = client.post("/api/todos", json={
        "title": "Daily Task",
        "due_date": "2026-07-29",
        "recurring": "daily",
    })
    assert resp.status_code == 201
    assert resp.json()["recurring"] == "daily"


def test_toggle_recurring_creates_next(client):
    """Check that completing a recurring todo creates the next instance."""
    resp = client.post("/api/todos", json={
        "title": "Weekly Standup",
        "due_date": "2026-07-27",  # Monday
        "recurring": "weekly",
    })
    tid = resp.json()["id"]

    # Toggle (complete)
    resp = client.patch(f"/api/todos/{tid}/toggle")
    assert resp.status_code == 200
    data = resp.json()

    # Current should be completed
    assert data["todo"]["completed"] is True

    # Next instance should be created
    assert data["next"] is not None
    assert data["next"]["due_date"] == "2026-08-03"  # Next Monday
    assert data["next"]["title"] == "Weekly Standup"
    assert data["next"]["recurring"] == "weekly"
    assert data["next"]["completed"] is False


def test_untoggle_recurring_does_not_duplicate(client):
    """Toggling a recurring todo back to incomplete should not create
    another next instance, and should leave it incomplete again."""
    resp = client.post("/api/todos", json={
        "title": "Weekly Standup",
        "due_date": "2026-07-27",
        "recurring": "weekly",
    })
    tid = resp.json()["id"]

    # Complete it: creates the next instance.
    resp = client.patch(f"/api/todos/{tid}/toggle")
    assert resp.json()["todo"]["completed"] is True
    assert resp.json()["next"] is not None

    # Toggle again: should flip back to incomplete, no second next instance.
    resp = client.patch(f"/api/todos/{tid}/toggle")
    data = resp.json()
    assert data["todo"]["completed"] is False
    assert data["next"] is None

    assert len(client.get("/api/todos").json()) == 2  # original + next only


def test_toggle_one_shot_no_next(client):
    """Non-recurring toggle should not create a next instance."""
    resp = client.post("/api/todos", json={"title": "One Shot"})
    tid = resp.json()["id"]
    resp = client.patch(f"/api/todos/{tid}/toggle")
    data = resp.json()
    assert data["todo"]["completed"] is True
    assert data["next"] is None


def test_recurring_monthly_advance(client):
    """Monthly should advance to same day next month."""
    resp = client.post("/api/todos", json={
        "title": "Monthly Bill",
        "due_date": "2026-01-31",
        "recurring": "monthly",
    })
    tid = resp.json()["id"]
    resp = client.patch(f"/api/todos/{tid}/toggle")
    # Jan 31 → Feb 28 (2026 is not a leap year)
    assert resp.json()["next"]["due_date"] == "2026-02-28"


def test_recurring_yearly_leap_day(client):
    resp = client.post("/api/todos", json={
        "title": "Leap Day",
        "due_date": "2028-02-29",
        "recurring": "yearly",
    })
    tid = resp.json()["id"]
    resp = client.patch(f"/api/todos/{tid}/toggle")
    assert resp.status_code == 200
    assert resp.json()["next"]["due_date"] == "2029-02-28"


# ── Undo delete ───────────────────────────────────────────────


def test_undo_delete(client):
    resp = client.post("/api/todos", json={"title": "Oops"})
    tid = resp.json()["id"]

    # Delete
    client.delete(f"/api/todos/{tid}")
    resp = client.get(f"/api/todos/{tid}")
    assert resp.status_code == 404

    # Undo
    resp = client.post(f"/api/todos/{tid}/undo")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["todo"]["title"] == "Oops"

    # Should be back
    resp = client.get(f"/api/todos/{tid}")
    assert resp.status_code == 200


def test_undo_nonexistent(client):
    resp = client.post("/api/todos/nonexistent/undo")
    assert resp.status_code == 404


# ── Notify field ──────────────────────────────────────────────


def test_notify_at_field(client):
    resp = client.post("/api/todos", json={
        "title": "Remind Me",
        "notify_at": "due",
    })
    assert resp.status_code == 201
    assert resp.json()["notify_at"] == "due"


# ── Filter modes ──────────────────────────────────────────────


def test_filter_today(client):
    import time
    today = time.strftime("%Y-%m-%d")
    client.post("/api/todos", json={"title": "Today", "due_date": today})
    client.post("/api/todos", json={"title": "Tomorrow", "due_date": "2099-12-31"})
    resp = client.get("/api/todos?filter=today")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Today"


def test_filter_week(client):
    import time
    from datetime import datetime, timedelta
    today = time.strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    far = "2099-12-31"
    client.post("/api/todos", json={"title": "Now", "due_date": today})
    client.post("/api/todos", json={"title": "Soon", "due_date": tomorrow})
    client.post("/api/todos", json={"title": "Later", "due_date": far})
    resp = client.get("/api/todos?filter=week")
    data = resp.json()
    titles = {t["title"] for t in data}
    assert "Now" in titles
    assert "Soon" in titles
    assert "Later" not in titles
