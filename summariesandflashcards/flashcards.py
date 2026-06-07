"""Generate Anki flashcards from a grounded summary and export to an .apkg deck.

Cards are generated from the finished summary (not the raw source): the summary is
already gated and faithful, so cards derived from it inherit that faithfulness. The
prompt hard-restricts the model to facts present in the summary. One LLM call per
topic (a `parts`-split of the summary) — small focused calls produce valid JSON far
more reliably on a 3B model than one large call.
"""

from __future__ import annotations

import json
import os
import re
import tempfile

import genanki

from summariesandflashcards.config import OLLAMA_HOST, TEXT_MODEL

# Fixed IDs (generated once with `random.randrange(1 << 30, 1 << 31)`). Anki uses
# these to identify the note model and deck on import — they must stay constant.
_MODEL_ID = 1090544029
_DECK_ID = 1676386282

_MODEL = genanki.Model(
    _MODEL_ID,
    "Summaries and Flashcards Q&A",
    fields=[{"name": "Question"}, {"name": "Answer"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Question}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Answer}}',
        }
    ],
)

# Strip ```json … ``` fences and pull out the first [...] array the model emitted.
_FENCE_RE = re.compile(r"```[a-zA-Z]*")
_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
# Fallback: capture "q": "...", "a": "..." pairs directly, tolerating escaped quotes.
# Used when json.loads fails on malformed structure (e.g. a 3B model's stray `}}`
# or trailing commas) — the pairs are still recoverable even if the braces aren't.
_PAIR_RE = re.compile(
    r'"q"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"a"\s*:\s*"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)


def _unescape(s: str) -> str:
    """Turn a raw JSON string body into its decoded value; fall back to as-is."""
    try:
        return json.loads(f'"{s}"')
    except (json.JSONDecodeError, ValueError):
        return s


def _parse_cards(raw: str) -> list[tuple[str, str]]:
    """Extract (question, answer) pairs from a model response.

    Tolerant of code fences, surrounding prose, and the malformed-but-recoverable
    JSON small models emit. Returns [] if nothing parses.
    """
    text = _FENCE_RE.sub("", raw).strip()
    cards: list[tuple[str, str]] = []

    # Strict path first — preserves intended ordering and exact values.
    match = _ARRAY_RE.search(text)
    if match:
        try:
            items = json.loads(match.group(0))
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        q = str(item.get("q", "")).strip()
                        a = str(item.get("a", "")).strip()
                        if q and a:
                            cards.append((q, a))
                if cards:
                    return cards
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback — recover q/a pairs from structurally-broken JSON.
    for q_raw, a_raw in _PAIR_RE.findall(text):
        q = _unescape(q_raw).strip()
        a = _unescape(a_raw).strip()
        if q and a:
            cards.append((q, a))
    return cards


def _generate_for_text(client, model: str, text: str, n: int) -> list[tuple[str, str]]:
    """One grounded generation call for a single topic, with one repair retry."""
    from summariesandflashcards.prompts import flashcard_prompt

    prompt = flashcard_prompt(text, n)
    for _ in range(2):
        try:
            resp = client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
                stream=False,
            )
            cards = _parse_cards(resp["message"]["content"])
            if cards:
                return cards
        except Exception:
            pass
    return []


def generate_cards(
    parts: list[str],
    model: str = TEXT_MODEL,
    host: str = OLLAMA_HOST,
    per_part: int = 2,
    max_total: int = 20,
) -> list[tuple[str, str]]:
    """Generate flashcards from summary topic parts, deduped and capped.

    Args:
        parts:     Summary split into topic chunks (the done-stage `parts`).
        per_part:  Target cards per topic.
        max_total: Hard cap on the returned deck size.
    """
    from ollama import Client

    client = Client(host=host)
    seen: set[str] = set()
    cards: list[tuple[str, str]] = []

    for part in parts:
        if len(cards) >= max_total:
            break
        if not part.strip():
            continue
        for q, a in _generate_for_text(client, model, part, per_part):
            key = q.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            cards.append((q, a))
            if len(cards) >= max_total:
                break
    return cards


def build_apkg(cards: list[tuple[str, str]], deck_name: str = "Summaries and Flashcards") -> bytes:
    """Build an Anki .apkg deck from (question, answer) pairs and return its bytes.

    genanki only writes to a path, so we round-trip through a temp file.
    """
    deck = genanki.Deck(_DECK_ID, deck_name)
    for q, a in cards:
        deck.add_note(genanki.Note(model=_MODEL, fields=[q, a]))

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".apkg", delete=False) as tmp:
            tmp_path = tmp.name
        genanki.Package(deck).write_to_file(tmp_path)
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
