"""Pydantic models for toodoo API."""
from pydantic import BaseModel
from typing import Optional


class TodoCreate(BaseModel):
    title: str
    notes: Optional[str] = ""
    due_date: Optional[str] = ""   # YYYY-MM-DD
    due_time: Optional[str] = ""   # HH:MM


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    completed: Optional[bool] = None
    sort_order: Optional[float] = None


class TodoResponse(BaseModel):
    id: str
    title: str
    notes: str = ""
    due_date: str = ""
    due_time: str = ""
    completed: bool = False
    sort_order: float = 0
    created_at: str = ""
    updated_at: str = ""
