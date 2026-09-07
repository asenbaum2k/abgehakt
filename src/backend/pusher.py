"""
abgehakt push notification daemon.

Polls the SQLite DB for todos whose notification time has been reached
and sends a push via the self-hosted ntfy server.

Runs standalone (not inside FastAPI):
    python3 pusher.py

Config via environment or .env file in this directory:
    NTFY_URL         default http://100.103.1.124:2586
    NTFY_TOPIC       default abgehakt
    NTFY_USER        required for auth (admin user)
    NTFY_PASSWORD    required for auth
    NTFY_CLICK_URL   default http://100.103.1.124:8766/ (opened on tap)
    APP_TIMEZONE     default Europe/Berlin (DB times are local wall-clock)
    POLL_INTERVAL    seconds between polls, default 30
    GRACE_MINUTES    max lateness to still send a push, default 180
                     (older ones are marked notified without sending,
                     so a server downtime doesn't cause a push storm)
"""
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from email.header import Header
from zoneinfo import ZoneInfo

import httpx

from database import DB_PATH

# ── Config ──────────────────────────────────────────────────


def _load_dotenv(path):
    """Minimal .env loader (KEY=VALUE lines, # comments)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

NTFY_URL = os.environ.get("NTFY_URL", "http://100.103.1.124:2586").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "abgehakt")
NTFY_USER = os.environ.get("NTFY_USER", "")
NTFY_PASSWORD = os.environ.get("NTFY_PASSWORD", "")
NTFY_CLICK_URL = os.environ.get("NTFY_CLICK_URL", "http://100.103.1.124:8766/")
APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Europe/Berlin")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
GRACE_MINUTES = int(os.environ.get("GRACE_MINUTES", "180"))

APP_TZ = ZoneInfo(APP_TIMEZONE)

# notify_at value -> timedelta offset from the due datetime
NOTIFY_OFFSETS = {
    "due": timedelta(0),
    "5min_before": timedelta(minutes=-5),
    "15min_before": timedelta(minutes=-15),
    "1h_before": timedelta(hours=-1),
    "1day_before": timedelta(days=-1),
}


# ── Core logic (pure, testable) ─────────────────────────────


def compute_notify_dt(todo: dict, tz: ZoneInfo = APP_TZ) -> datetime | None:
    """Compute the moment a notification should fire, in tz-aware time.

    DB stores local wall-clock values (due_date 'YYYY-MM-DD',
    due_time 'HH:MM') plus the notify_at offset. Returns None when the
    todo is not notifiable (missing data or unknown notify_at).
    """
    notify_at = (todo.get("notify_at") or "").strip()
    due_date = (todo.get("due_date") or "").strip()
    due_time = (todo.get("due_time") or "").strip()
    if not notify_at or not due_date or not due_time:
        return None
    offset = NOTIFY_OFFSETS.get(notify_at)
    if offset is None:
        return None
    try:
        due_dt = datetime.strptime(f"{due_date} {due_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return due_dt.replace(tzinfo=tz) + offset


def is_notifiable(todo: dict) -> bool:
    """Basic row-level filter before computing times."""
    if todo.get("completed"):
        return False
    if (todo.get("notified_at") or "").strip():
        return False
    return True


def due_for_notification(todo: dict, now: datetime,
                         grace: timedelta) -> str:
    """Decide what to do with a todo whose notify_dt was computed.

    Returns 'send', 'skip_late' (mark notified, don't send) or 'wait'.
    """
    notify_dt = compute_notify_dt(todo)
    if notify_dt is None:
        return "wait"
    if notify_dt > now:
        return "wait"
    if now - notify_dt > grace:
        return "skip_late"
    return "send"


# ── DB helpers ──────────────────────────────────────────────


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_candidates(conn) -> list[dict]:
    """All open, not-yet-notified todos with notify_at set."""
    rows = conn.execute("""
        SELECT * FROM todos
        WHERE notify_at != '' AND completed = 0
          AND (notified_at IS NULL OR notified_at = '')
    """).fetchall()
    return [dict(r) for r in rows]


def mark_notified(conn, todo_id: str):
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("UPDATE todos SET notified_at = ? WHERE id = ?",
                 (stamp, todo_id))
    conn.commit()


# ── Push ────────────────────────────────────────────────────


def encode_title(title: str) -> str:
    """RFC-2047-encode a title for the ntfy Title header.

    HTTP headers are ASCII-only in httpx; ntfy decodes RFC 2047
    (=?utf-8?b?...?=) on the server side, so emojis/umlauts survive.
    Pure-ASCII titles pass through unchanged.
    """
    title = title[:200]
    try:
        title.encode("ascii")
        return title
    except UnicodeEncodeError:
        # NB: Header() must get BYTES, and .encode() (not str()) produces
        # the wire format — str() returns the decoded form unchanged.
        return Header(title.encode("utf-8"), "utf-8").encode()


def send_push(todo: dict) -> bool:
    """Send one push via ntfy. Returns True on HTTP 2xx."""
    notify_dt = compute_notify_dt(todo)
    when = notify_dt.astimezone(APP_TZ).strftime("%H:%M") if notify_dt else ""
    due_label = f"{todo['due_date']} {todo['due_time']}".strip()
    body = f"Fällig: {due_label}"
    if (todo.get("notes") or "").strip():
        body += f"\n{todo['notes'].strip()[:200]}"

    headers = {
        "Title": encode_title(todo["title"]),
        "Priority": "4",
        "Tags": "alarm_clock,abgehakt",
        "Click": NTFY_CLICK_URL,
    }
    auth = (NTFY_USER, NTFY_PASSWORD) if NTFY_USER else None
    try:
        resp = httpx.post(f"{NTFY_URL}/{NTFY_TOPIC}", content=body,
                          headers=headers, auth=auth, timeout=10)
        if resp.is_success:
            print(f"[{datetime.now(APP_TZ):%H:%M:%S}] ✅ Push: "
                  f"{todo['title']!r} (fällig {due_label}, Erinnerung {when})")
            return True
        print(f"[{datetime.now(APP_TZ):%H:%M:%S}] ⚠️ ntfy HTTP "
              f"{resp.status_code} für {todo['title']!r}: {resp.text[:200]}")
    except httpx.HTTPError as e:
        print(f"[{datetime.now(APP_TZ):%H:%M:%S}] ⚠️ Push-Fehler für "
              f"{todo['title']!r}: {e}")
    return False


# ── Main loop ───────────────────────────────────────────────


def poll_once(grace: timedelta) -> tuple[int, int]:
    """One poll cycle. Returns (sent, skipped_late)."""
    sent = skipped = 0
    with _connect() as conn:
        now = datetime.now(APP_TZ)
        for todo in fetch_candidates(conn):
            if not is_notifiable(todo):
                continue
            decision = due_for_notification(todo, now, grace)
            if decision == "send":
                if send_push(todo):
                    mark_notified(conn, todo["id"])
                    sent += 1
                # on failure: leave notified_at empty -> retry next cycle
            elif decision == "skip_late":
                mark_notified(conn, todo["id"])
                skipped += 1
                print(f"[{datetime.now(APP_TZ):%H:%M:%S}] ⏭️  zu alt, "
                      f"kein Push: {todo['title']!r}")
    return sent, skipped


def main():
    if not NTFY_USER or not NTFY_PASSWORD:
        print("❌ NTFY_USER / NTFY_PASSWORD nicht gesetzt "
              "(Env oder .env). Abbruch.")
        sys.exit(1)
    grace = timedelta(minutes=GRACE_MINUTES)
    print(f"🔔 abgehakt-pusher gestartet | ntfy: {NTFY_URL}/{NTFY_TOPIC} | "
          f"TZ: {APP_TIMEZONE} | Intervall: {POLL_INTERVAL}s | "
          f"Grace: {GRACE_MINUTES}min")
    while True:
        try:
            poll_once(grace)
        except sqlite3.Error as e:
            print(f"[{datetime.now(APP_TZ):%H:%M:%S}] ⚠️ DB-Fehler: {e}")
        except Exception as e:  # keep daemon alive no matter what
            print(f"[{datetime.now(APP_TZ):%H:%M:%S}] ⚠️ Unerwartet: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
