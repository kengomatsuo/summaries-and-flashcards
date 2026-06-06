import re
import time
from collections.abc import Iterator, Callable
from ollama import Client
from summariesandflashcards.config import OLLAMA_HOST, CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS, GROUP_SIZE
from summariesandflashcards.prompts import (
    summary_prompt, map_prompt, adjacency_prompt, group_reduce_prompt,
    link_prompt, reduce_prompt,
    auto_depth, DEPTH_OPTIONS, PROFICIENCY_OPTIONS,
)


def needs_mapreduce(text: str) -> bool:
    """Use map-reduce whenever there is more than one section chunk."""
    return len(chunk_text(text)) > 1


def _paragraph_chunk(text: str) -> list[str]:
    """Paragraph-aware fallback for sections too large to fit in one chunk."""
    paragraphs = [p.strip() for p in re.split(r'\n\n+', text) if p.strip()]
    if not paragraphs:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > CHUNK_MAX_CHARS:
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sent in sentences:
                if current and len(current) + len(sent) + 1 > CHUNK_MAX_CHARS:
                    chunks.append(current)
                    current = sent
                else:
                    current = (current + " " + sent).strip() if current else sent
        elif current and len(current) + len(para) + 2 > CHUNK_MAX_CHARS:
            chunks.append(current)
            current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para
    if current:
        chunks.append(current)
    return chunks or [text]


def chunk_text(text: str) -> list[str]:
    """Split at Markdown heading boundaries; paragraph fallback for oversized sections."""
    sections = re.split(r'(?m)(?=^#{1,6} [A-Z0-9])', text)
    sections = [s.strip() for s in sections if s.strip()]

    if not sections:
        return _paragraph_chunk(text)

    chunks: list[str] = []
    current = ""

    for section in sections:
        if len(section) > CHUNK_MAX_CHARS:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_paragraph_chunk(section))
        elif current and len(current) + len(section) + 2 > CHUNK_MAX_CHARS:
            chunks.append(current)
            current = section
        else:
            current = (current + "\n\n" + section).strip() if current else section

    if current:
        chunks.append(current)

    return chunks or [text]


def _extract_title(chunk: str) -> str:
    """Return the first meaningful line of a chunk as its section title."""
    for line in chunk.splitlines():
        clean = line.strip().lstrip('#').strip()
        if clean:
            return clean[:80]
    return "Section"


_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 2.0

ProgressCallback = Callable[[str, float], None] | None


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
    """Parse a yes/no response. Raises ValueError if the answer is unclear."""
    first = text.strip().lower().split()
    if not first:
        raise ValueError("Empty response")
    word = first[0].rstrip(".,!?")
    if word == "yes":
        return True
    if word == "no":
        return False
    raise ValueError(f"Unclear response: {text!r}")


def _topic_group(
    items: list[tuple[str, str]],
    client: Client,
    model: str,
    tick: Callable[[str, float], None] | None = None,
    base_pct: float = 0.4,
) -> list[list[tuple[str, str]]]:
    """Group adjacent (title, summary) pairs that belong to the same topic.

    For each consecutive pair, asks the LLM: "Is B a continuation/application of A?"
    Adjacent 'yes' answers are merged into one group. Falls back to a new group on
    unclear answers (after retries) so the pipeline never stalls.

    Groups are capped at GROUP_SIZE as a safety net against unusually long topic runs.
    """
    if len(items) <= 1:
        return [items] if items else []

    n = len(items)
    groups: list[list[tuple[str, str]]] = [[items[0]]]

    for i in range(1, n):
        if tick:
            tick(f"Grouping section {i + 1} of {n}…", base_pct + (i / n) * 0.15)

        title_a, summary_a = items[i - 1]
        title_b, summary_b = items[i]
        prompt = adjacency_prompt(title_a, summary_a, title_b, summary_b)

        def ask(p=prompt):
            return _parse_yes_no(_collect(client, model, p))

        try:
            same_topic = _with_retry(ask)
        except Exception:
            same_topic = False  # safe fallback: start a new group

        if same_topic and len(groups[-1]) < GROUP_SIZE:
            groups[-1].append(items[i])
        else:
            groups.append([items[i]])

    return groups


def summarize_stream(
    text: str,
    model: str,
    depth: str,
    proficiency: str = "Intermediate",
) -> Iterator[str]:
    """Single-pass streaming summary for single-section documents."""
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
) -> Iterator[str]:
    """Five-phase pipeline for multi-section documents:

    1. Map      — summarise each section chunk independently (no cross-chunk context)
    2. Group    — sequential adjacency checks: merge chunks on the same topic so
                  exercises land next to their theory
    3. Reduce   — one LLM call per topic group to synthesise theory + exercises together
    4. Link     — analyse connections across topic-group summaries
    5. Reduce   — streaming final summary with depth/proficiency applied
    """
    def _prog(msg: str, pct: float) -> None:
        if on_progress:
            on_progress(msg, pct)

    chunks = chunk_text(text)
    n_chunks = len(chunks)
    client = Client(host=OLLAMA_HOST)

    # Phase 1: Map  (0 → 40%)
    items: list[tuple[str, str]] = []
    for i, chunk in enumerate(chunks):
        _prog(f"Summarising section {i + 1} of {n_chunks}…", (i / n_chunks) * 0.4)
        title = _extract_title(chunk)
        prompt = map_prompt(chunk, proficiency)
        summary = _with_retry(lambda p=prompt: _collect(client, model, p))
        items.append((title, summary))

    # Phase 2: Topic grouping  (40 → 55%)
    _prog("Grouping related sections…", 0.4)
    groups = _topic_group(items, client, model, tick=on_progress, base_pct=0.4)
    n_groups = len(groups)

    # Phase 3: Group reduce  (55 → 75%)
    group_summaries: list[str] = []
    for i, group in enumerate(groups):
        _prog(f"Synthesising topic {i + 1} of {n_groups}…", 0.55 + (i / n_groups) * 0.2)
        if len(group) == 1:
            group_summaries.append(group[0][1])
        else:
            prompt = group_reduce_prompt(group, proficiency)
            group_summaries.append(_with_retry(lambda p=prompt: _collect(client, model, p)))

    # Phase 4: Link  (75 → 88%)
    _prog("Analysing connections between topics…", 0.75)
    connection_analysis = _with_retry(
        lambda: _collect(client, model, link_prompt(group_summaries))
    )

    # Phase 5: Final reduce — streaming  (88% → done)
    _prog("Writing final summary…", 0.88)
    numbered = "\n\n".join(f"[{i}] {s}" for i, s in enumerate(group_summaries))
    final_prompt = reduce_prompt(numbered, depth, proficiency, connection_analysis)
    stream = _with_retry(lambda: client.chat(
        model=model,
        messages=[{"role": "user", "content": final_prompt}],
        stream=True,
    ))
    for chunk in stream:
        token = chunk["message"]["content"]
        if token:
            yield token
