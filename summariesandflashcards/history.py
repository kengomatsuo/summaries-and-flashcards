"""Persistent run history stored in history.json at the project root."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

_HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "history.json")
_MAX_RUNS = 20


def _save(history: list[dict]) -> None:
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def append_run(
    files: list[str],
    model: str,
    depth: str,
    proficiency: str,
    summary: str,
    group_labels: list[str] | None = None,
) -> str:
    """Insert a new run at the front of history. Returns the run's unique id."""
    history = load_history()
    run_id = uuid.uuid4().hex
    history.insert(0, {
        "id": run_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "files": files,
        "model": model,
        "depth": depth,
        "proficiency": proficiency,
        "summary": summary,
        "group_labels": group_labels or [],
        "flashcards": [],   # accumulates across generations: [{"q","a"}, ...]
        "used_parts": [],   # summary topic indices already turned into cards
    })
    history = history[:_MAX_RUNS]
    _save(history)
    return run_id


def save_flashcards(
    run_id: str,
    cards: list[tuple[str, str]],
    used_parts: list[int],
) -> None:
    """Persist a run's full flashcard deck + used topics (best-effort).

    The session is the source of truth for the live deck; this just mirrors it to
    disk so it survives a revisit. No-ops if the run has no id or has scrolled out
    of history (e.g. legacy runs created before ids existed).
    """
    if not run_id:
        return
    history = load_history()
    entry = next((r for r in history if r.get("id") == run_id), None)
    if entry is None:
        return
    entry["flashcards"] = [{"q": q, "a": a} for q, a in cards]
    entry["used_parts"] = sorted(set(int(i) for i in used_parts))
    _save(history)


def load_history() -> list[dict]:
    if not os.path.exists(_HISTORY_FILE):
        return []
    try:
        with open(_HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []
