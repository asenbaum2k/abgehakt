"""
abgehakt v2 — FastAPI backend for the smart to-do list.
Runs on localhost:8766, accessible via Tailscale.
"""
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import (
    init_db, get_all_todos, get_all_tags,
    add_todo, get_todo, update_todo, delete_todo,
    complete_recurring, undo_delete_todo,
)
from models import (
    TodoCreate, TodoUpdate, TodoResponse,
    RecurringToggleResult, UndoResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="abgehakt API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_response(todo: dict) -> dict:
    """Convert DB row to JSON-safe response dict."""
    if not todo:
        return None
    todo["completed"] = bool(todo["completed"])
    for f in ("recurring", "recurring_anchor", "tags", "notify_at"):
        if f not in todo:
            todo[f] = ""
    return todo


# ── API Routes ──────────────────────────────────────────────


@app.get("/api/todos")
async def list_todos(
    filter: str = Query("all", pattern="^(all|today|week)$"),
    tag: str = Query("", description="Filter by exact tag name"),
):
    """Get all todos. Filter: all, today, week. Optional tag filter."""
    todos = get_all_todos(filter_mode=filter, tag_filter=tag or None)
    result = [_to_response(t) for t in todos]
    return result


@app.get("/api/tags")
async def list_tags():
    """Return all distinct tags."""
    return get_all_tags()


@app.post("/api/todos", status_code=201)
async def create_todo(item: TodoCreate):
    """Add a new todo."""
    if not item.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    todo_id = str(uuid.uuid4())
    result = add_todo(
        todo_id,
        item.title.strip(),
        notes=(item.notes or "").strip(),
        due_date=(item.due_date or "").strip(),
        due_time=(item.due_time or "").strip(),
        recurring=(item.recurring or "").strip(),
        recurring_anchor=(item.recurring_anchor or "").strip(),
        tags=(item.tags or "").strip(),
        notify_at=(item.notify_at or "").strip(),
    )
    return _to_response(result)


@app.get("/api/todos/{todo_id}")
async def read_todo(todo_id: str):
    """Get a single todo."""
    todo = _to_response(get_todo(todo_id))
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo


@app.patch("/api/todos/{todo_id}")
async def patch_todo(todo_id: str, updates: TodoUpdate):
    """Update a todo (any fields)."""
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = update_todo(todo_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Todo not found")
    return _to_response(result)


@app.patch("/api/todos/{todo_id}/toggle", response_model=RecurringToggleResult)
async def toggle_todo(todo_id: str):
    """Toggle complete. For recurring todos: creates next instance."""
    todo, next_todo = complete_recurring(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return RecurringToggleResult(
        todo=TodoResponse(**_to_response(todo)),
        next=TodoResponse(**_to_response(next_todo)) if next_todo else None,
    )


@app.delete("/api/todos/{todo_id}")
async def remove_todo(todo_id: str):
    """Delete a todo (soft: archived for undo)."""
    result = delete_todo(todo_id)
    if not result:
        raise HTTPException(status_code=404, detail="Todo not found")
    result["completed"] = bool(result["completed"])
    return {"deleted": _to_response(result)}


@app.post("/api/todos/{todo_id}/undo", response_model=UndoResponse)
async def undo_delete(todo_id: str):
    """Undo a deletion."""
    todo = undo_delete_todo(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Nothing to undo")
    return UndoResponse(success=True, todo=TodoResponse(**_to_response(todo)))


# ── Serve frontend ──────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    print(f"[Frontend] Serving from {FRONTEND_DIR}")


# ── Run ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("✅ abgehakt v2 starting on http://localhost:8766")
    uvicorn.run(app, host="0.0.0.0", port=8766)
