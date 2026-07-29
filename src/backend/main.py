"""
abgehakt — FastAPI backend for the smart to-do list.
Runs on localhost:8766, accessible via Tailscale.
"""
import os
import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db, get_all_todos, add_todo, get_todo, update_todo, delete_todo
from models import TodoCreate, TodoUpdate

app = FastAPI(title="abgehakt API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()


# ── API Routes ──────────────────────────────────────────────


@app.get("/api/todos")
async def list_todos(filter: str = Query("all", regex="^(all|today|week)$")):
    """Get all todos. Filter: all, today, week."""
    todos = get_all_todos(filter_mode=filter)
    for t in todos:
        t["completed"] = bool(t["completed"])
    return todos


@app.post("/api/todos", status_code=201)
async def create_todo(item: TodoCreate):
    """Add a new todo."""
    if not item.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    todo_id = str(uuid.uuid4())
    result = add_todo(
        todo_id,
        item.title.strip(),
        item.notes.strip() if item.notes else "",
        item.due_date or "",
        item.due_time or "",
    )
    result["completed"] = bool(result["completed"])
    return result


@app.get("/api/todos/{todo_id}")
async def read_todo(todo_id: str):
    """Get a single todo."""
    todo = get_todo(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    todo["completed"] = bool(todo["completed"])
    return todo


@app.patch("/api/todos/{todo_id}")
async def patch_todo(todo_id: str, updates: TodoUpdate):
    """Update a todo (title, notes, dates, completed, sort_order)."""
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = update_todo(todo_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Todo not found")
    result["completed"] = bool(result["completed"])
    return result


@app.patch("/api/todos/{todo_id}/toggle")
async def toggle_todo(todo_id: str):
    """Quick toggle: mark done / undo."""
    todo = get_todo(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    result = update_todo(todo_id, {"completed": not bool(todo["completed"])})
    result["completed"] = bool(result["completed"])
    return result


@app.delete("/api/todos/{todo_id}")
async def remove_todo(todo_id: str):
    """Delete a todo."""
    result = delete_todo(todo_id)
    if not result:
        raise HTTPException(status_code=404, detail="Todo not found")
    result["completed"] = bool(result["completed"])
    return {"deleted": result}


# ── Serve frontend ──────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    print(f"[Frontend] Serving from {FRONTEND_DIR}")


# ── Run ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("✅ abgehakt starting on http://localhost:8766")
    uvicorn.run(app, host="0.0.0.0", port=8766)
