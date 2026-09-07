"""Pydantic models for abgehakt v2 API."""
from pydantic import BaseModel
from typing import Optional, List


class TodoCreate(BaseModel):
    title: str
    notes: Optional[str] = ""
    due_date: Optional[str] = ""   # YYYY-MM-DD
    due_time: Optional[str] = ""   # HH:MM
    recurring: Optional[str] = ""  # "" | "daily" | "weekly" | "monthly" | "yearly"
    recurring_anchor: Optional[str] = ""  # original due date for context
    tags: Optional[str] = ""       # comma-separated tags
    notify_at: Optional[str] = ""  # "due" | "5min_before" etc.


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    recurring: Optional[str] = None
    recurring_anchor: Optional[str] = None
    tags: Optional[str] = None
    notify_at: Optional[str] = None
    completed: Optional[bool] = None
    sort_order: Optional[float] = None


class TodoResponse(BaseModel):
    id: str
    title: str
    notes: str = ""
    due_date: str = ""
    due_time: str = ""
    recurring: str = ""
    recurring_anchor: str = ""
    tags: str = ""
    notify_at: str = ""
    completed: bool = False
    sort_order: float = 0
    created_at: str = ""
    updated_at: str = ""


class RecurringToggleResult(BaseModel):
    todo: TodoResponse
    next: Optional[TodoResponse] = None


class UndoResponse(BaseModel):
    success: bool
    todo: Optional[TodoResponse] = None
