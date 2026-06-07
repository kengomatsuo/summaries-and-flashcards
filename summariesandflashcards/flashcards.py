"""Generate Anki flashcards from a grounded summary and export to an .apkg deck.

Cards are generated from the finished summary (not the raw source): the summary is
already gated and faithful, so cards derived from it inherit that faithfulness. The
prompt hard-restricts the model to facts present in the summary. One LLM call per
topic (a `parts`-split of the summary) — small focused calls produce valid JSON far
more reliably on a 3B model than one large call.
"""

from __future__ import annotations

import html
import json
import os
import re
import tempfile

import genanki
import latex2mathml.converter
import markdown as _markdown

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


# Self-contained flip-card widget — inlined HTML/CSS/JS, no external resources, so it
# works fully offline. Embedded via st.iframe (sandboxed iframe, raw-HTML src), so its JS
# (flip/navigate) runs client-side without triggering Streamlit reruns. `__CARDS_JSON__`
# is replaced with the card data — pre-rendered, escaped HTML assigned via innerHTML.
_WIDGET_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
         Helvetica, Arial, sans-serif; background: transparent; }
  #wrap { display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 32px 8px; }
  .scene { width: 100%; max-width: 540px; height: 220px; perspective: 1200px; }
  .card { position: relative; width: 100%; height: 100%; cursor: pointer;
          transform-style: preserve-3d; transition: transform .5s; }
  .card.flipped { transform: rotateY(180deg); }
  .face { position: absolute; inset: 0; backface-visibility: hidden;
          -webkit-backface-visibility: hidden; display: flex; flex-direction: column;
          align-items: center; justify-content: center; padding: 28px 24px; text-align: center;
          border: 1px solid #e3e3e3; border-radius: 14px; background: #fff;
          box-shadow: 0 4px 14px rgba(0,0,0,.08); overflow: auto; }
  .front { color: #1a1a1a; font-size: 20px; font-weight: 600; line-height: 1.4; }
  .back { color: #1a1a1a; font-size: 18px; line-height: 1.5; transform: rotateY(180deg); }
  .face p { margin: .25em 0; }
  .face code { background: #f0f0f0; padding: 1px 5px; border-radius: 4px; font-size: .9em;
               font-family: ui-monospace, Menlo, Consolas, monospace; }
  .face ul, .face ol { text-align: left; display: inline-block; margin: .25em 0; padding-left: 1.3em; }
  .face math { font-size: 1.05em; }
  .mathblock { display: block; text-align: center; margin: 10px 0; }
  .tag { position: absolute; top: 12px; left: 16px; font-size: 11px; letter-spacing: .08em;
         text-transform: uppercase; color: #9a9a9a; }
  .hint { position: absolute; bottom: 10px; right: 16px; font-size: 11px; color: #c2c2c2; }
  .controls { display: flex; align-items: center; gap: 18px; }
  button { font: inherit; font-size: 14px; padding: 6px 16px; border: 1px solid #d0d0d0;
           border-radius: 8px; background: #fff; color: #1a1a1a; cursor: pointer; }
  button:hover:not(:disabled) { background: #f3f3f3; }
  button:disabled { opacity: .4; cursor: default; }
  #counter { font-size: 13px; color: #666; min-width: 60px; text-align: center; }
</style></head>
<body>
  <div id="wrap">
    <div class="scene"><div class="card" id="card">
      <div class="face front"><span class="tag">Question</span><div id="q"></div>
        <span class="hint">click to flip</span></div>
      <div class="face back"><span class="tag">Answer</span><div id="a"></div></div>
    </div></div>
    <div class="controls">
      <button id="prev">&lsaquo; Prev</button>
      <span id="counter"></span>
      <button id="next">Next &rsaquo;</button>
    </div>
  </div>
  <script>
    const cards = __CARDS_JSON__;
    let i = 0;
    const card = document.getElementById('card');
    const q = document.getElementById('q'), a = document.getElementById('a');
    const counter = document.getElementById('counter');
    const prev = document.getElementById('prev'), next = document.getElementById('next');
    function render() {
      card.classList.remove('flipped');
      q.innerHTML = cards[i][0];
      a.innerHTML = cards[i][1];
      counter.textContent = (i + 1) + ' / ' + cards.length;
      prev.disabled = i === 0;
      next.disabled = i === cards.length - 1;
    }
    card.addEventListener('click', () => card.classList.toggle('flipped'));
    prev.addEventListener('click', () => { if (i > 0) { i--; render(); } });
    next.addEventListener('click', () => { if (i < cards.length - 1) { i++; render(); } });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft' && i > 0) { i--; render(); }
      else if (e.key === 'ArrowRight' && i < cards.length - 1) { i++; render(); }
      else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); card.classList.toggle('flipped'); }
    });
    render();
  </script>
</body></html>"""


# Math rendering: $$…$$ → block MathML, $…$ → inline MathML (browser-native, so the
# widget needs no JS/fonts and stays fully offline). Markdown handles bold/code/lists.
_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\$(.+?)\$", re.DOTALL)


def _latex_to_mathml(latex: str, display: bool) -> str:
    try:
        ml = latex2mathml.converter.convert(latex.strip())
    except Exception:
        # Malformed LaTeX → show the literal (escaped) instead of crashing.
        delim = "$$" if display else "$"
        return html.escape(f"{delim}{latex}{delim}")
    return f'<div class="mathblock">{ml}</div>' if display else ml


def _render_md_math(text: str) -> str:
    """Render a card's markdown + LaTeX (`$…$`/`$$…$$`) to safe HTML.

    Math is pulled out and converted to MathML first (placeholder-protected); the
    remaining text is HTML-escaped (so model output can't inject tags) before
    Markdown runs; then the trusted MathML is reinserted.
    """
    stash: dict[str, str] = {}

    def _protect(match: re.Match, display: bool) -> str:
        token = f"@@MATH{len(stash)}@@"
        stash[token] = _latex_to_mathml(match.group(1), display)
        return token

    text = _DISPLAY_MATH_RE.sub(lambda m: _protect(m, True), text)
    text = _INLINE_MATH_RE.sub(lambda m: _protect(m, False), text)
    out = _markdown.markdown(html.escape(text), extensions=["sane_lists", "nl2br"])
    for token, ml in stash.items():
        out = out.replace(token, ml)
    return out


def cards_widget_html(cards: list[tuple[str, str]]) -> str:
    """Build a self-contained, offline flip-card widget for the given cards.

    Each card's question/answer is rendered (markdown + MathML) to HTML, then
    JSON-encoded with `<`/`>`/`&` escaped — which both prevents a `</script>`
    breakout AND decodes back to real tags when the widget assigns innerHTML.
    """
    rendered = [[_render_md_math(q), _render_md_math(a)] for q, a in cards]
    data = json.dumps(rendered)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return _WIDGET_TEMPLATE.replace("__CARDS_JSON__", data)


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
