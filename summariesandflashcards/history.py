"""Persistent run history stored in history.json at the project root."""

from __future__ import annotations

import json
import os
from datetime import datetime

_HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "history.json")
_MAX_RUNS = 20


def append_run(
    files: list[str],
    model: str,
    depth: str,
    proficiency: str,
    summary: str,
    group_labels: list[str] | None = None,
) -> None:
    history = load_history()
    history.insert(0, {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "files": files,
        "model": model,
        "depth": depth,
        "proficiency": proficiency,
        "summary": summary,
        "group_labels": group_labels or [],
    })
    history = history[:_MAX_RUNS]
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def load_history() -> list[dict]:
    if not os.path.exists(_HISTORY_FILE):
        return []
    try:
        with open(_HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []
