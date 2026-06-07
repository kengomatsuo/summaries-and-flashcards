import re
import time
from collections.abc import Iterator, Callable
from typing import Any
from ollama import Client
from summariesandflashcards.config import OLLAMA_HOST, GROUP_SIZE, MIN_GROUP_WORDS
from summariesandflashcards.prompts import (
    skim_prompt, adjacency_prompt, summary_prompt,
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
        options={"temperature": 0},  # faithful, deterministic skim/grouping
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


# ── Skim output parser ────────────────────────────────────────────────────────

def _parse_skim(raw: str) -> tuple[str, str]:
    """Extract (label, context) from a skim_prompt response.

    Expects:
        TOPIC: <short label>
        CONTEXT: <1-2 sentences>

    Falls back gracefully if the model doesn't follow the format exactly.
    """
    label = ""
    context = ""
    for line in raw.splitlines():
        s = line.strip()
        if not label and s.upper().startswith("TOPIC:"):
            label = s[6:].strip()[:80]
        elif not context and s.upper().startswith("CONTEXT:"):
            context = s[8:].strip()
    if not label:
        label = raw.strip()[:80]
    if not context:
        context = label
    return label, context


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

# ── Hallucination gates ───────────────────────────────────────────────────────
# Gate A: count only *teachable* words — strip file headers, image captions, and
# "STEP n OF m" labels — so a bare title/label/picture slide reads as near-empty.
_FILE_HEADER_RE = re.compile(r'^#*\s*File \d+ of \d+:.*$', re.MULTILINE)
# Vision captions are appended AFTER the text of each section by ingest.py, so
# everything from the first "[Image:" to the end of a section is caption. Matching
# to end-of-section (not to the first "]") is robust to "]" inside a caption,
# e.g. an array index like "System[n]".
_IMAGE_BLOCK_RE = re.compile(r'\[Image:.*', re.DOTALL)
_STEP_LABEL_RE = re.compile(r'\bSTEP \d+ OF \d+\b', re.IGNORECASE)
_WORD_RE = re.compile(r'[A-Za-z]{2,}')

# Gate B: strip the model's habitual narration opener (kept short so the topic
# noun that follows survives, e.g. "The lecture covered image processing" →
# "Image processing"). Only the lead phrase is removed, never a whole sentence.
_OPENER_RE = re.compile(
    r'^\s*(?:'
    r'the\s+(?:lecture|slides?|section|notes?|text)\s+'
    r'(?:covered|covers|discussed|discusses|introduced|introduces|explained|explains|'
    r'described|describes|presented|presents|outlined|outlines|'
    r'focused\s+on|focuses\s+on|touched\s+on|touches\s+on)\s+'
    r'|this\s+(?:slide|section|lecture|chapter|part)\s+'
    r'(?:covered|covers|discussed|discusses|introduced|introduces|explained|explains|'
    r'described|describes|presented|presents|is\s+about)\s+'
    r'|in\s+this\s+(?:slide|section|lecture)[,]?\s+'
    r')',
    re.IGNORECASE,
)


def _teachable_word_count(section: str) -> int:
    """Words in ONE section after removing its header, trailing caption, and labels.

    Counted per section because captions trail each section individually — a text
    section that follows an image section in the same group must still be counted.
    """
    section = _FILE_HEADER_RE.sub('', section)
    section = _IMAGE_BLOCK_RE.sub('', section)
    section = _STEP_LABEL_RE.sub('', section)
    return len(_WORD_RE.findall(section))


def _group_teachable_words(group: list[tuple[str, str, str, str]]) -> int:
    return sum(_teachable_word_count(raw) for _, _, _, raw in group)


def _group_text(group: list[tuple[str, str, str, str]]) -> str:
    return "\n\n".join(raw for _, _, _, raw in group)


def _strip_opener(text: str) -> str:
    """Remove a leading 'The lecture covered…'-style narration phrase."""
    stripped = _OPENER_RE.sub('', text, count=1)
    if stripped != text:
        stripped = stripped.lstrip()
        if stripped:
            stripped = stripped[0].upper() + stripped[1:]
    return stripped


def _is_skip(text: str) -> bool:
    """True if the model declined the section (SKIP sentinel) or returned nothing.

    Covers the degenerate one-word non-answers small models emit instead of
    following the SKIP instruction: "None", "N/A", "(none)".
    """
    t = text.strip().rstrip('.').strip().upper()
    return t in ("", "SKIP", "NONE", "N/A", "(NONE)")


# A "SKIP" on its own line anywhere in the lead (some models prepend prose).
_SKIP_LINE_RE = re.compile(r'(?m)^\s*SKIP[\s.]*$')

# Verbose refusals: a weak model sometimes narrates "there is no content here"
# instead of emitting the SKIP sentinel. Anchored to notes/theory/summary wording
# so it does not fire on a genuine summary that merely starts with "There is no…".
_REFUSAL_RE = re.compile(
    r"^\s*(?:"
    r"i\s+(?:don'?t|do\s+not|can'?t|cannot)\s+see\s+(?:any\s+)?"
    r"(?:lecture\s+)?(?:theory|content|notes?|summary|information)"
    r"|there\s+(?:is|are)\s+no\s+(?:detailed\s+|summary\s+of\s+|actual\s+)?"
    r"(?:lecture\s+)?(?:theory|content|summary|information|notes?)"
    r"|unfortunately,?\s+there\s+(?:is|are)\s+no\s+(?:lecture\s+)?(?:theory|content)"
    r"|(?:the\s+)?notes?\s+(?:do\s+not|don'?t)\s+contain\s+(?:any\s+)?"
    r"(?:lecture\s+)?(?:theory|content)"
    r")",
    re.IGNORECASE,
)


def _declines(lead: str) -> bool:
    """True if the lead is a SKIP sentinel or a verbose refusal to summarise."""
    t = lead.strip()
    return _is_skip(t) or bool(_SKIP_LINE_RE.search(t)) or bool(_REFUSAL_RE.match(t))


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
    items: list[tuple[str, str, str, str]],  # (title, label, context, raw_chunk)
    client: Client,
    model: str,
    tick: Callable[[str, float], None] | None = None,
    base_pct: float = 0.45,
) -> list[list[tuple[str, str, str, str]]]:
    """Group consecutive items whose context descriptions indicate the same topic.

    Adjacency check: context[i-1] vs context[i] → same topic? yes/no.
    Falls back to new group on unclear answer. Capped at GROUP_SIZE.
    """
    if len(items) <= 1:
        return [items] if items else []

    n = len(items)
    groups: list[list[tuple[str, str, str, str]]] = [[items[0]]]

    for i in range(1, n):
        if tick:
            tick(f"Categorising section {i + 1} of {n}…", base_pct + (i / n) * 0.2)

        _, _, context_a, _ = items[i - 1]
        _, _, context_b, _ = items[i]
        prompt = adjacency_prompt(context_a, context_b)

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
        options={"temperature": 0},
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
    items: list[tuple[str, str, str, str]] = []
    for i, chunk in enumerate(all_chunks):
        _prog(f"Reading section {i + 1} of {n_chunks}…", 0.2 + (i / n_chunks) * 0.25)
        title = _extract_title(chunk)
        raw_skim = _with_retry(lambda c=chunk: _collect(client, model, skim_prompt(c)))
        label, context = _parse_skim(raw_skim)
        items.append((title, label, context, chunk))
        logger.log_skim(i, title, label, context, chunk)
        _step("section", (i, n_chunks, title, label))

    # ── Phase 2: Group  (45 → 65%) ───────────────────────────────────────────
    _prog("Categorising topics…", 0.45)
    groups = _topic_group(items, client, model, tick=on_progress, base_pct=0.45)

    # Gate A — drop groups with no teachable content BEFORE the writer sees them.
    # A small model handed a bare title/label/picture slide invents a whole
    # lecture; the only reliable fix is to never ask it. Fall back to all groups
    # if everything is thin, so we never produce an empty summary.
    kept_groups = [g for g in groups if _group_teachable_words(g) >= MIN_GROUP_WORDS]
    groups = kept_groups or groups

    logger.log_groups(groups)
    _step("groups", groups)

    # ── Phase 3: Write  (65 → 100%) — stream each group directly ─────────────
    # Gate B runs here: the lead of each group is buffered just long enough to
    # (a) strip the "The lecture covered…" narration opener and (b) honour a SKIP
    # sentinel, then the rest streams live. A separator is emitted only between
    # groups that actually produce content, so SKIPs leave no empty parts.
    n_groups = len(groups)
    tokens_collected: list[str] = []
    written_labels: list[str] = []
    emitted_any = False

    for i, group in enumerate(groups):
        _prog(f"Summarising topic {i + 1} of {n_groups}…", 0.65 + (i / n_groups) * 0.35)
        group_text = _group_text(group)
        prompt = summary_prompt(group_text, depth, proficiency)
        stream = _with_retry(lambda p=prompt: client.chat(
            model=model,
            messages=[{"role": "user", "content": p}],
            options={"num_predict": 2000, "temperature": 0},
            stream=True,
        ))

        lead = ""          # buffered head of the output, until we decide
        decided = False    # have we committed to emitting this group?
        skipped = False    # did the model return SKIP / nothing?
        pending_sep = "\n\n---\n\n" if emitted_any else ""

        def _commit(text: str):
            """Emit the cleaned lead, with a separator if earlier groups wrote."""
            nonlocal emitted_any
            if pending_sep:
                tokens_collected.append(pending_sep)
                yield pending_sep
            written_labels.append(group[0][0][:40])
            emitted_any = True
            tokens_collected.append(text)
            yield text

        with logger.open_group_write(i, group, group_text) as write_token:
            for chunk in stream:
                token = chunk["message"]["content"]
                if not token:
                    continue
                write_token(token)
                if skipped:
                    continue
                if decided:
                    tokens_collected.append(token)
                    yield token
                    continue
                lead += token
                if "\n" not in lead and len(lead) < 100:
                    continue
                decided = True
                if _declines(lead):
                    skipped = True
                else:
                    yield from _commit(_strip_opener(lead.lstrip()))

            # Stream ended before the lead buffer tripped the threshold.
            if not decided and not skipped and not _declines(lead):
                yield from _commit(_strip_opener(lead.lstrip()))

    _step("written_labels", written_labels)
    logger.log_summary("".join(tokens_collected))
