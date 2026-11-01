"""
Task Manager — track tasks, deadlines, reminders.
Persists to data/tasks.json.
"""

import json
import os
import datetime
from pathlib import Path

TASKS_FILE = Path(__file__).parent.parent / "data" / "tasks.json"


class TaskManager:
    def __init__(self):
        self.tasks: list[dict] = []
        self._load()

    def _load(self):
        if TASKS_FILE.exists():
            with open(TASKS_FILE, "r") as f:
                self.tasks = json.load(f)

    def _save(self):
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TASKS_FILE, "w") as f:
            json.dump(self.tasks, f, indent=2, default=str)

    def add_task(self, title: str, deadline: str = None, category: str = "general") -> dict:
        task = {
            "id": len(self.tasks) + 1,
            "title": title,
            "category": category,
            "deadline": deadline,
            "status": "pending",
            "created_at": datetime.datetime.now().isoformat(),
            "completed_at": None,
        }
        self.tasks.append(task)
        self._save()
        return task

    def complete_task(self, task_id: int) -> dict | None:
        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = "done"
                task["completed_at"] = datetime.datetime.now().isoformat()
                self._save()
                return task
        return None

    def get_pending(self) -> list[dict]:
        return [t for t in self.tasks if t["status"] == "pending"]

    def get_overdue(self) -> list[dict]:
        now = datetime.datetime.now()
        overdue = []
        for t in self.tasks:
            if t["status"] == "pending" and t.get("deadline"):
                try:
                    dl = datetime.datetime.fromisoformat(t["deadline"])
                    if dl < now:
                        overdue.append(t)
                except ValueError:
                    pass
        return overdue

    def get_summary(self) -> str:
        pending = self.get_pending()
        overdue = self.get_overdue()
        if not pending:
            return "No pending tasks."
        lines = [f"📋 {len(pending)} pending tasks ({len(overdue)} overdue):"]
        for t in pending:
            marker = "🔴" if t in overdue else "⏳"
            dl = f" (due: {t['deadline']})" if t.get("deadline") else ""
            lines.append(f"  {marker} #{t['id']}: {t['title']}{dl}")
        return "\n".join(lines)
