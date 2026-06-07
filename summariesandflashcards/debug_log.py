"""Live debug logging for the summariesandflashcards pipeline.

Each run writes to logs/<ISO-timestamp>/ in the project root.
Files are written immediately as events happen — if a run crashes
mid-way, everything up to the crash is still on disk.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

_PROJECT_ROOT = Path(__file__).parent.parent
_LOG_DIR = _PROJECT_ROOT / "logs"


def new_run_dir() -> Path:
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    d = _LOG_DIR / stamp
    d.mkdir(parents=True, exist_ok=True)
    return d


class RunLogger:
    def __init__(self, run_dir: Path) -> None:
        self.d = run_dir

    # ── helpers ──────────────────────────────────────────────────────────────

    def _write(self, name: str, content: str, mode: str = "w") -> None:
        with (self.d / name).open(mode, encoding="utf-8") as f:
            f.write(content)

    def _append(self, name: str, content: str) -> None:
        self._write(name, content, "a")

    # ── Phase 0: raw input ────────────────────────────────────────────────────

    def log_input(self, combined: str) -> None:
        self._write("00_input.txt", combined)

    # ── Phase 0: segmentation ─────────────────────────────────────────────────

    def log_segments(self, fi: int, file_name: str, sections: list[str], method: str) -> None:
        """One call per file after splitting into sections."""
        header = (
            f"{'='*70}\n"
            f"File {fi + 1}: {file_name}\n"
            f"Method : {method}\n"
            f"Sections: {len(sections)}\n"
            f"{'='*70}\n"
        )
        body = ""
        for i, s in enumerate(sections):
            body += f"\n--- Section {i + 1} ({len(s)} chars) ---\n{s}\n"
        self._append("01_segments.txt", header + body + "\n")

    # ── Phase 1: skim ─────────────────────────────────────────────────────────

    def log_skim(self, i: int, title: str, label: str, raw: str) -> None:
        """One call per section after LLM label."""
        block = (
            f"--- Section {i + 1} ---\n"
            f"Title  : {title}\n"
            f"Label  : {label}\n"
            f"Raw    :\n{raw}\n"
            f"{'-'*50}\n\n"
        )
        self._append("02_skim.txt", block)

    # ── Phase 2: groups ───────────────────────────────────────────────────────

    def log_groups(self, groups: list[list[tuple[str, str, str]]]) -> None:
        """Called once after grouping completes."""
        lines = [f"{len(groups)} groups total\n\n"]
        for i, group in enumerate(groups):
            titles = " | ".join(t for t, _, _ in group)
            labels = " | ".join(lab for _, lab, _ in group)
            lines.append(
                f"Group {i + 1} ({len(group)} sections)\n"
                f"  Titles : {titles}\n"
                f"  Labels : {labels}\n\n"
            )
        self._write("03_groups.txt", "".join(lines))

    # ── Phase 3: write ────────────────────────────────────────────────────────

    @contextmanager
    def open_group_write(
        self,
        group_idx: int,
        group: list[tuple[str, str, str]],
        raw_text: str,
    ) -> "Generator[None, None, None]":
        """Context manager that keeps a log file open during LLM streaming.

        Usage::

            with logger.open_group_write(i, group, group_text) as write_token:
                for chunk in stream:
                    token = chunk["message"]["content"]
                    if token:
                        write_token(token)
                        yield token
        """
        fname = f"04_write_group_{group_idx + 1:02d}.txt"
        titles = " | ".join(t for t, _, _ in group)
        labels = " | ".join(lab for _, lab, _ in group)
        header = (
            f"{'='*70}\n"
            f"Group {group_idx + 1} ({len(group)} sections)\n"
            f"Titles : {titles}\n"
            f"Labels : {labels}\n"
            f"{'='*70}\n\n"
            f"--- Raw text sent to LLM ({len(raw_text)} chars) ---\n"
            f"{raw_text}\n\n"
            f"{'='*70}\n"
            f"--- LLM output ---\n"
        )
        path = self.d / fname
        path.write_text(header, encoding="utf-8")
        with path.open("a", encoding="utf-8") as fh:
            def write_token(token: str) -> None:
                fh.write(token)
                fh.flush()

            yield write_token

    # ── Phase 3: final summary ────────────────────────────────────────────────

    def log_summary(self, text: str) -> None:
        self._write("05_summary.txt", text)
