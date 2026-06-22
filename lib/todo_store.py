#!/usr/bin/env python3
"""todo_store.py — Simple in-memory todo list for MiMo Agent."""
import uuid
import time

_todos: list = []


def add_todo(content: str) -> dict:
    item = {
        "id": uuid.uuid4().hex[:8],
        "content": content,
        "status": "pending",
        "created": time.time(),
    }
    _todos.append(item)
    return item


def get_todos() -> list:
    return list(_todos)


def mark_done(todo_id: str) -> bool:
    for t in _todos:
        if t["id"] == todo_id:
            t["status"] = "done"
            return True
    return False


def clear_todos() -> int:
    count = len(_todos)
    _todos.clear()
    return count
