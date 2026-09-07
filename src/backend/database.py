"""
SQLite database module for abgehakt v2.
Uses a single file (todos.db) — no server, no config.
Migration-aware: updates schema from v1 → v2.
"""
import sqlite3
import os
import time

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "todos.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate_v2(conn):
    """Add v2 columns and tables if they don't exist (idempotent)."""
    # Check if recurring columns exist
    cols = {row[1] for row in conn.execute("PRAGMA table_info(todos)").fetchall()}

    if "recurring" not in cols:
        conn.execute("ALTER TABLE todos ADD COLUMN recurring TEXT DEFAULT ''")
        print("[DB] Migration: added recurring column")
    if "recurring_anchor" not in cols:
        conn.execute("ALTER TABLE todos ADD COLUMN recurring_anchor TEXT DEFAULT ''")
        print("[DB] Migration: added recurring_anchor column")
    if "tags" not in cols:
        conn.execute("ALTER TABLE todos ADD COLUMN tags TEXT DEFAULT ''")
        print("[DB] Migration: added tags column")
    if "notify_at" not in cols:
        conn.execute("ALTER TABLE todos ADD COLUMN notify_at TEXT DEFAULT ''")
        print("[DB] Migration: added notify_at column")

    # Tags master table (for listing all unique tags)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tag_index (
            tag TEXT PRIMARY KEY,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Soft-delete / undo table for swipe-to-delete
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deleted_todos (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            notes TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            due_time TEXT DEFAULT '',
            recurring TEXT DEFAULT '',
            recurring_anchor TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            notify_at TEXT DEFAULT '',
            completed INTEGER DEFAULT 0,
            sort_order REAL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            deleted_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)


def _rebuild_tag_index(conn):
    """Rebuild tag_index from all todo tags."""
    conn.execute("DELETE FROM tag_index")
    rows = conn.execute("SELECT tags FROM todos WHERE tags != ''").fetchall()
    tags_seen = set()
    for (tag_str,) in rows:
        for tag in tag_str.split(","):
            tag = tag.strip()
            if tag:
                tags_seen.add(tag)
    for tag in sorted(tags_seen):
        conn.execute(
            "INSERT OR IGNORE INTO tag_index (tag) VALUES (?)", (tag,)
        )


def init_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                notes TEXT DEFAULT '',
                due_date TEXT DEFAULT '',
                due_time TEXT DEFAULT '',
                completed INTEGER DEFAULT 0,
                sort_order REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        _migrate_v2(conn)
        _rebuild_tag_index(conn)
    print(f"[DB] Ready at {DB_PATH}")


# ── Todo CRUD ────────────────────────────────────────────────


def get_all_todos(filter_mode="all", tag_filter=None):
    """Get all todos sorted. Supports tag filtering."""
    today = time.strftime("%Y-%m-%d")

    with _get_conn() as conn:
        base = "SELECT * FROM todos"
        where = []
        params = []

        if filter_mode == "today":
            where.append("due_date = ?")
            params.append(today)
        elif filter_mode == "week":
            where.append("due_date >= ? AND due_date <= date(?, '+6 days')")
            params.extend([today, today])

        if tag_filter:
            # Match comma-separated tags with LIKE
            where.append("(tags = ? OR tags LIKE ? OR tags LIKE ? OR tags LIKE ?)")
            params.extend([
                tag_filter,
                f"{tag_filter},%",
                f"%,{tag_filter},%",
                f"%,{tag_filter}",
            ])

        sql = base
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY completed ASC, sort_order ASC"

        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_all_tags():
    """Return list of all distinct tags."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT tag FROM tag_index ORDER BY tag"
        ).fetchall()
    return [r[0] for r in rows]


def _update_tag_index(conn, tag_str: str):
    """Ensure tags from tag_str exist in tag_index."""
    if not tag_str:
        return
    for tag in tag_str.split(","):
        tag = tag.strip()
        if tag:
            conn.execute(
                "INSERT OR IGNORE INTO tag_index (tag) VALUES (?)", (tag,)
            )


def add_todo(todo_id, title, notes="", due_date="", due_time="",
             recurring="", recurring_anchor="", tags="", notify_at=""):
    with _get_conn() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM todos"
        ).fetchone()[0]

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO todos (id, title, notes, due_date, due_time,
                               recurring, recurring_anchor, tags, notify_at,
                               sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (todo_id, title, notes, due_date, due_time,
              recurring, recurring_anchor, tags, notify_at,
              max_order + 1, now, now))
        _update_tag_index(conn, tags)

    return get_todo(todo_id)


def get_todo(todo_id):
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    return dict(row) if row else None


def update_todo(todo_id, updates):
    allowed = {
        "title", "notes", "due_date", "due_time", "completed",
        "sort_order", "recurring", "recurring_anchor", "tags", "notify_at",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not filtered:
        return get_todo(todo_id)

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    filtered["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in filtered)
    values = list(filtered.values()) + [todo_id]

    with _get_conn() as conn:
        conn.execute(f"UPDATE todos SET {set_clause} WHERE id = ?", values)
        if "tags" in filtered:
            _rebuild_tag_index(conn)

    return get_todo(todo_id)


def delete_todo(todo_id):
    """Delete a todo, archiving to deleted_todos for undo."""
    todo = get_todo(todo_id)
    if todo:
        with _get_conn() as conn:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                INSERT INTO deleted_todos
                    (id, title, notes, due_date, due_time, recurring,
                     recurring_anchor, tags, notify_at, completed,
                     sort_order, created_at, updated_at, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                todo["id"], todo["title"], todo.get("notes", ""),
                todo.get("due_date", ""), todo.get("due_time", ""),
                todo.get("recurring", ""), todo.get("recurring_anchor", ""),
                todo.get("tags", ""), todo.get("notify_at", ""),
                todo["completed"], todo.get("sort_order", 0),
                todo.get("created_at", ""), todo.get("updated_at", ""),
                now,
            ))
            conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            _rebuild_tag_index(conn)
    return todo


def undo_delete_todo(todo_id):
    """Restore the most recently deleted todo by id."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM deleted_todos WHERE id = ? ORDER BY deleted_at DESC LIMIT 1",
            (todo_id,),
        ).fetchone()
        if not row:
            return None
        deleted = dict(row)
        conn.execute("""
            INSERT INTO todos (id, title, notes, due_date, due_time,
                               recurring, recurring_anchor, tags, notify_at,
                               completed, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            deleted["id"], deleted["title"], deleted["notes"],
            deleted["due_date"], deleted["due_time"],
            deleted.get("recurring", ""), deleted.get("recurring_anchor", ""),
            deleted.get("tags", ""), deleted.get("notify_at", ""),
            deleted["completed"], deleted.get("sort_order", 0),
            deleted.get("created_at", ""), deleted.get("updated_at", ""),
        ))
        conn.execute("DELETE FROM deleted_todos WHERE id = ?", (todo_id,))
        _update_tag_index(conn, deleted.get("tags", ""))
    return get_todo(todo_id)


# ── Recurring logic ──────────────────────────────────────────


def _advance_date(due_date: str, interval: str) -> str:
    """Advance due_date by the recurring interval.
    Returns new date string YYYY-MM-DD or '' if can't compute.
    """
    if not due_date or not interval:
        return ""
    from datetime import datetime as dt, timedelta
    try:
        d = dt.strptime(due_date, "%Y-%m-%d")
    except ValueError:
        return ""

    if interval == "daily":
        d = d + timedelta(days=1)
    elif interval == "weekly":
        d = d + timedelta(weeks=1)
    elif interval == "monthly":
        # Same day next month, handling month boundaries
        month = d.month + 1
        year = d.year
        if month > 12:
            month = 1
            year += 1
        day = d.day
        # Handle short months by clamping
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(day, max_day)
        d = d.replace(year=year, month=month, day=day)
    elif interval == "yearly":
        import calendar
        target_year = d.year + 1
        day = min(d.day, calendar.monthrange(target_year, d.month)[1])
        d = d.replace(year=target_year, day=day)
    else:
        return ""

    return d.strftime("%Y-%m-%d")


def complete_recurring(todo_id):
    """Complete a recurring todo and create the next instance,
    or complete a one-shot todo normally. Returns (result_todo, next_todo_or_None).
    """
    todo = get_todo(todo_id)
    if not todo:
        return None, None

    recurring = (todo.get("recurring") or "").strip()
    due_date = (todo.get("due_date") or "").strip()

    # If not recurring, just toggle done
    if not recurring:
        result = update_todo(todo_id, {"completed": not bool(todo["completed"])})
        return result, None

    # Mark current as completed
    result = update_todo(todo_id, {"completed": True})

    # Create next instance only if currently un-completed and has a due date
    if not bool(todo["completed"]):
        next_date = _advance_date(due_date, recurring)
        if next_date:
            import uuid
            next_id = str(uuid.uuid4())
            next_todo = add_todo(
                next_id,
                todo["title"],
                notes=todo.get("notes", ""),
                due_date=next_date,
                due_time=todo.get("due_time", ""),
                recurring=recurring,
                recurring_anchor=todo.get("recurring_anchor", ""),
                tags=todo.get("tags", ""),
                notify_at=todo.get("notify_at", ""),
            )
            return result, next_todo

    return result, None
