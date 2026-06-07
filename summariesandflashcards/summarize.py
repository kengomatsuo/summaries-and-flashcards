import re
import time
from collections.abc import Iterator, Callable
from typing import Any
from ollama import Client
from summariesandflashcards.config import OLLAMA_HOST, GROUP_SIZE
from summariesandflashcards.prompts import (
    label_prompt, adjacency_prompt, summary_prompt,
    auto_depth, DEPTH_OPTIONS, PROFICIENCY_OPTIONS,
)
from summariesandflashcards.debug_log import RunLogger, new_run_dir

# ── Retry / collect helpers ───────────────────────────────────────────────────

_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 2.0

ProgressCallback = Callable[[str, float], None] | None
StepCallback = Callable[[str, Any], None] | None


def _with_retry(fn: Callable, retries: int = _RETRY_ATTEMPTS, delay: float = _RETRY_DELAY):
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _collect(client: Client, model: str, prompt: str) -> str:
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    return response["message"]["content"]


def _parse_yes_no(text: str) -> bool:
    first = text.strip().lower().split()
    if not first:
        raise ValueError("Empty response")
    word = first[0].rstrip(".,!?")
    if word == "yes":
        return True
    if word == "no":
        return False
    raise ValueError(f"Unclear response: {text!r}")


# ── Title extraction ──────────────────────────────────────────────────────────

def _extract_title(chunk: str) -> str:
    """First meaningful line — skips page numbers, file headers, and short fragments."""
    for line in chunk.splitlines():
        clean = line.strip().lstrip('#').strip()
        if (clean
                and len(clean) >= 3
                and not re.fullmatch(r'\d+', clean)
                and not re.match(r'File \d+ of \d+:', clean)):
            return clean[:80]
    return "Section"


# ── Segmentation — no LLM needed ─────────────────────────────────────────────

_GARBAGE_RE = re.compile(r'^[\|\-\s:=]+$')
_MEANINGFUL_RE = re.compile(r'[a-zA-Z]{5,}')


def _split_sections(text: str) -> tuple[list[str], str]:
    """Split one file's text into sections.

    Strategy:
      - If the text contains form-feed characters (\\x0c), each one marks a
        slide/page boundary — split there.
      - Otherwise the paragraphs (\\n\\n-delimited blocks) are already
        roughly slide-sized — use them directly.

    Sections are filtered for content quality:
      - Pure separator rows (only pipe/dash/space chars) are dropped.
      - Sections with no word of 5+ alphabetic chars are dropped — these are
        garbled image slides, math notation fragments, or empty pages that the
        LLM would hallucinate content for.

    Returns (sections, method) where method is a short label for debug logs.
    """
    if '\x0c' in text:
        raw = [s.strip() for s in text.split('\x0c')]
        method = "form-feed (\\x0c)"
    else:
        raw = [s.strip() for s in re.split(r'\n\n+', text)]
        method = "paragraph (\\n\\n)"

    sections = [
        s for s in raw
        if s
        and not _GARBAGE_RE.match(s)
        and _MEANINGFUL_RE.search(s)
    ]
    return (sections or [text]), method


# ── Topic grouping ────────────────────────────────────────────────────────────

def _topic_group(
    items: list[tuple[str, str, str]],  # (title, label, raw_chunk)
    client: Client,
    model: str,
    tick: Callable[[str, float], None] | None = None,
    base_pct: float = 0.45,
) -> list[list[tuple[str, str, str]]]:
    """Group consecutive items whose labels indicate the same topic.

    Adjacency check: label[i-1] vs label[i] → same topic? yes/no.
    Falls back to new group on unclear answer. Capped at GROUP_SIZE.
    """
    if len(items) <= 1:
        return [items] if items else []

    n = len(items)
    groups: list[list[tuple[str, str, str]]] = [[items[0]]]

    for i in range(1, n):
        if tick:
            tick(f"Categorising section {i + 1} of {n}…", base_pct + (i / n) * 0.2)

        _, label_a, _ = items[i - 1]
        _, label_b, _ = items[i]
        prompt = adjacency_prompt(label_a, label_b)

        def ask(p=prompt):
            return _parse_yes_no(_collect(client, model, p))

        try:
            same_topic = _with_retry(ask)
        except Exception:
            same_topic = False

        if same_topic and len(groups[-1]) < GROUP_SIZE:
            groups[-1].append(items[i])
        else:
            groups.append([items[i]])

    return groups


# ── Public API ────────────────────────────────────────────────────────────────

def summarize_stream(
    text: str,
    model: str,
    depth: str,
    proficiency: str = "Intermediate",
) -> Iterator[str]:
    """Single-pass streaming summary — kept for edge-case use."""
    prompt = summary_prompt(text, depth, proficiency)
    client = Client(host=OLLAMA_HOST)
    stream = _with_retry(lambda: client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    ))
    for chunk in stream:
        token = chunk["message"]["content"]
        if token:
            yield token


def summarize_mapreduce(
    text: str,
    model: str,
    depth: str,
    proficiency: str = "Intermediate",
    on_progress: ProgressCallback = None,
    on_step: StepCallback = None,
) -> Iterator[str]:
    """Four-phase pipeline — each agent handles one small, focused task:

    Phase 0 — SEGMENT  split by \\x0c (form feeds) if present, else by paragraphs
    Phase 1 — SKIM     one LLM call per section → 5-word topic label
    Phase 2 — GROUP    one LLM call per consecutive pair → same topic?
    Phase 3 — WRITE    one streaming LLM call per topic group → summary from raw text
                       (depth + proficiency applied here on focused single-topic text)

    on_step events:
      ("segment", (fi, n_files, file_name, n_sections))  — after each file is segmented
      ("section", (i,  n_chunks, title,     label))       — after each section is labelled
      ("groups",  list[list[tuple[str,str,str]]])         — after grouping
    """
    def _prog(msg: str, pct: float) -> None:
        if on_progress:
            on_progress(msg, pct)

    def _step(event: str, data: Any) -> None:
        if on_step:
            on_step(event, data)

    client = Client(host=OLLAMA_HOST)
    logger = RunLogger(new_run_dir())

    # Recover per-file texts from the combined string app.py builds
    file_texts = [t.strip() for t in re.split(r'\n\n---\n\n', text) if t.strip()]
    n_files = len(file_texts)

    logger.log_input(text)

    # ── Phase 0: Segment  (0 → 20%) ──────────────────────────────────────────
    all_chunks: list[str] = []
    for fi, file_text in enumerate(file_texts):
        _prog(f"Segmenting file {fi + 1} of {n_files}…", (fi / n_files) * 0.2)

        parts = file_text.split('\n', 1)
        file_header = parts[0].strip()                         # "# File 1 of 5: foo.pdf"
        content = parts[1].strip() if len(parts) > 1 else ""
        file_name = re.sub(r'^#+\s*', '', file_header)         # strip leading #

        sections, seg_method = _split_sections(content) if content else ([file_text], "fallback")

        # Keep file header on first section so the model knows the source
        sections[0] = file_header + "\n\n" + sections[0]

        logger.log_segments(fi, file_name, sections, seg_method)
        all_chunks.extend(sections)
        _step("segment", (fi, n_files, file_name, len(sections)))

    n_chunks = len(all_chunks)

    # ── Phase 1: Skim  (20 → 45%) ────────────────────────────────────────────
    items: list[tuple[str, str, str]] = []
    for i, chunk in enumerate(all_chunks):
        _prog(f"Reading section {i + 1} of {n_chunks}…", 0.2 + (i / n_chunks) * 0.25)
        title = _extract_title(chunk)
        label = _with_retry(lambda c=chunk: _collect(client, model, label_prompt(c)))
        label = label.strip()[:80]
        items.append((title, label, chunk))
        logger.log_skim(i, title, label, chunk)
        _step("section", (i, n_chunks, title, label))

    # ── Phase 2: Group  (45 → 65%) ───────────────────────────────────────────
    _prog("Categorising topics…", 0.45)
    groups = _topic_group(items, client, model, tick=on_progress, base_pct=0.45)
    logger.log_groups(groups)
    _step("groups", groups)

    # ── Phase 3: Write  (65 → 100%) — stream each group directly ─────────────
    n_groups = len(groups)
    tokens_collected: list[str] = []
    for i, group in enumerate(groups):
        _prog(f"Summarising topic {i + 1} of {n_groups}…", 0.65 + (i / n_groups) * 0.35)
        group_text = "\n\n".join(raw for _, _, raw in group)
        prompt = summary_prompt(group_text, depth, proficiency)
        stream = _with_retry(lambda p=prompt: client.chat(
            model=model,
            messages=[{"role": "user", "content": p}],
            stream=True,
        ))
        with logger.open_group_write(i, group, group_text) as write_token:
            for chunk in stream:
                token = chunk["message"]["content"]
                if token:
                    write_token(token)
                    tokens_collected.append(token)
                    yield token

        if i < n_groups - 1:
            sep = "\n\n---\n\n"
            tokens_collected.append(sep)
            yield sep

    logger.log_summary("".join(tokens_collected))
