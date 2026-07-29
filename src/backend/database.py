"""
SQLite database module for abgehakt.
Uses a single file (todos.db) — no server, no config.
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
    print(f"[DB] Ready at {DB_PATH}")


def get_all_todos(filter_mode="all"):
    """Get all todos sorted. filter_mode: 'all', 'today', 'week'."""
    today = time.strftime("%Y-%m-%d")
    
    with _get_conn() as conn:
        if filter_mode == "today":
            rows = conn.execute("""
                SELECT * FROM todos
                WHERE due_date = ?
                ORDER BY completed ASC, sort_order ASC
            """, (today,)).fetchall()
        elif filter_mode == "week":
            # Simple: next 7 days (including today)
            # SQLite date functions handle this
            rows = conn.execute("""
                SELECT * FROM todos
                WHERE due_date >= ? AND due_date <= date(?, '+6 days')
                ORDER BY completed ASC, due_date ASC, sort_order ASC
            """, (today, today)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM todos
                ORDER BY completed ASC, sort_order ASC
            """).fetchall()
    
    return [dict(r) for r in rows]


def add_todo(todo_id, title, notes="", due_date="", due_time=""):
    with _get_conn() as conn:
        # Get next sort_order
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM todos"
        ).fetchone()[0]
        
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO todos (id, title, notes, due_date, due_time, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (todo_id, title, notes, due_date, due_time, max_order + 1, now, now))
    
    return get_todo(todo_id)


def get_todo(todo_id):
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    return dict(row) if row else None


def update_todo(todo_id, updates):
    allowed = {"title", "notes", "due_date", "due_time", "completed", "sort_order"}
    filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not filtered:
        return get_todo(todo_id)
    
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    filtered["updated_at"] = now
    
    set_clause = ", ".join(f"{k} = ?" for k in filtered)
    values = list(filtered.values()) + [todo_id]
    
    with _get_conn() as conn:
        conn.execute(f"UPDATE todos SET {set_clause} WHERE id = ?", values)
    
    return get_todo(todo_id)


def delete_todo(todo_id):
    todo = get_todo(todo_id)
    if todo:
        with _get_conn() as conn:
            conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    return todo
