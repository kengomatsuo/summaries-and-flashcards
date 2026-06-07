# Summaries and Flashcards — Architecture

## Project structure

```
Summaries and Flashcards/
├── app.py                    # Streamlit UI — state machine + pipeline orchestration
├── requirements.txt
├── summariesandflashcards/
│   ├── config.py             # Constants: model defaults, vision patterns, chunking limits
│   ├── ingest.py             # File-to-text extraction (PDF, PPTX, images, fallback)
│   ├── ollama_client.py      # Ollama health check, model listing, vision detection
│   ├── prompts.py            # All LLM prompt strings
│   ├── summarize.py          # Four-phase pipeline (Segment → Skim → Group → Write)
│   └── debug_log.py          # Per-run structured logging to logs/<timestamp>/
├── logs/                     # Debug output — one folder per summarise run (gitignored)
└── tests/                    # Sample lecture files for manual testing
```

---

## UI state machine

`app.py` drives three stages via `st.session_state.stage`:

```
idle → running → done
```

| Stage | What happens |
|---|---|
| **idle** | File upload widget, model/depth/proficiency controls, Summarise button |
| **running** | Pipeline executes synchronously; expander panels update live; `st.write_stream()` streams the summary token-by-token into the page |
| **done** | Fixed-height tabs (one per topic group) display the finished summary; download buttons |

Transition `running → done`: assembled summary is post-processed by `_fix_latex()`, stored in `session_state.last_summary`, then `st.rerun()` switches stage to `done`.

---

## Ingest (`summariesandflashcards/ingest.py`)

`extract_text(file_name, file_bytes, vision_model, client)` dispatches by file extension:

| Extension | Handler | Notes |
|---|---|---|
| `.pdf` | PyMuPDF — `_extract_pdf` | Per-page text + optional vision fallback |
| `.pptx` / `.ppt` | python-pptx — `_extract_pptx` | Per-slide text frames, tables, picture shapes |
| `.jpg`, `.png`, `.gif`, … | Direct vision — `_extract_image` | Whole file sent to vision model |
| Everything else | MarkItDown — `_extract_markitdown` | DOCX, XLSX, HTML, TXT, CSV, EPUB, MSG |

### Vision trigger (PDF, per page)

A page is rasterised (DPI controlled by `VISION_RASTER_DPI = 150` in config) and described by the vision model when **any** condition is true:

1. `page.get_images()` is non-empty — the page embeds raster images
2. No word of ≥5 alphabetic chars (`_MEANINGFUL_RE`) — text is garbled or absent
3. `_noise_ratio(text) > 0.35` — more than 35% of whitespace-separated tokens are ≤2 chars (equation-heavy pages)

The noise ratio catches equations typeset as PDF vector text — they contain real English words so condition 2 does not fire, but they also contain many single-char math symbols (`∂`, `ρ`, `=`, isolated letters) that push the ratio high.

### PPTX vision

Picture shapes (`shape.shape_type == MSO_SHAPE_TYPE.PICTURE`) are described individually. Text frames and table cells are extracted as plain text alongside the descriptions.

### Output format

Pages/slides are joined with form-feed `\x0c`. This character is the segmentation signal consumed by Phase 0 of the pipeline.

---

## Pipeline (`summariesandflashcards/summarize.py`)

`summarize_mapreduce()` is a generator that yields string tokens. Four sequential phases:

### Phase 0 — Segment (0 → 20%)

Splits each file's text into sections without an LLM:

- `\x0c` present → split on form feeds (one section per page/slide)
- Otherwise → split on `\n\n+` (paragraph blocks, which are already roughly slide-sized for most formats)

Filters applied to each candidate section:

- Drop pure separator rows matching `^[\|\-\s:=]+$`
- Drop sections with no word of ≥5 alphabetic chars (garbled or image-only pages that slipped through ingest)

### Phase 1 — Skim (20 → 45%)

One non-streaming LLM call per section → a 5-word topic label (`label_prompt()`).

Labels are stored alongside the raw chunk. They are **never** used as the input for summaries — only for grouping decisions. Summaries always operate on raw text.

### Phase 2 — Group (45 → 65%)

For each consecutive pair of labels, one LLM call (`adjacency_prompt()`) returns `yes` or `no`:

- `yes` → merge section into current group
- `no` → start a new group
- Hard cap: `GROUP_SIZE = 15` sections per group prevents over-merging when a topic dominates many consecutive slides

**Gate A — thin-group drop (anti-hallucination).** After grouping, any group whose *teachable* word count is below `MIN_GROUP_WORDS` (config, default 12) is dropped before the writer ever sees it. Teachable words are counted per section after stripping the file header, the trailing `[Image: …]` caption(s), and `STEP n OF m` labels — so a bare title slide, a one-word pipeline label (`Result`), or a picture-only slide reads as near-empty. The writer is never asked to summarise such a group, because a small model handed an empty slide invents a full lecture (`Result` → a sorting-algorithms lecture; a Mona Lisa caption → an image-processing lecture). If every group is thin, all are kept (never produce an empty summary). The filtered list is what Phase 3, the logs, and the UI group view all see, so tab labels stay aligned.

### Phase 3 — Write (65 → 100%)

One **streaming** LLM call per group. The raw text of all sections in the group is sent with `summary_prompt(depth, proficiency)`. Tokens are yielded directly to the UI.

**Gate B — opener strip + SKIP sentinel.** The lead of each group's output is buffered just long enough (first newline or 100 chars) to (a) strip the model's habitual `"The lecture covered…"` / `"This slide discusses…"` narration prefix — only the lead phrase, so the topic noun that follows survives — and (b) honour a `SKIP` sentinel: the write prompt instructs the model to reply `SKIP` for a section with no teachable content, and such groups emit nothing. After the lead is decided the rest streams live. A `\n\n---\n\n` separator is emitted only *between groups that actually wrote*, so dropped/SKIP groups leave no empty parts. The final labels of written groups are sent to the UI via the `written_labels` step event to keep tabs aligned.

Groups are separated in the output stream by `\n\n---\n\n`. The DONE stage splits on this delimiter to populate tabs.

Token cap: `options={"num_predict": 2000}` on every write call. Vision description calls use `{"num_predict": 1000}`.

---

## Debug logging (`summariesandflashcards/debug_log.py`)

Every summarise run writes to `logs/<ISO-8601-timestamp>/` in the project root:

| File | Contents |
|---|---|
| `00_input.txt` | Combined raw text passed to the pipeline |
| `01_segments.txt` | Sections after splitting and filtering, per file |
| `02_skim.txt` | Per-section title, label, and raw chunk |
| `03_groups.txt` | Final groupings with titles and labels |
| `04_write_group_NN.txt` | Raw text sent to LLM + LLM output, one file per group |
| `05_summary.txt` | Final assembled summary (after `\n\n---\n\n` separators) |

The `logs/` directory is gitignored.

---

## Vision model detection (`summariesandflashcards/ollama_client.py`)

`is_vision_model(name)` checks whether the lowercase model name contains any substring from `VISION_MODEL_PATTERNS` (defined in `config.py`). Models that match are tagged `(vision)` in the UI dropdown and are used for both text summarisation and image description during ingest.

---

## LaTeX rendering (`app.py`)

Streamlit's KaTeX renderer only accepts `$...$` (inline) and `$$...$$` (display) delimiters. Vision and write models tend to output `\(...\)` and `\[...\]` (standard LaTeX document convention).

`_fix_latex(text)` post-processes the assembled summary with two regexes before it is stored in session state:

```python
_DISPLAY_MATH_RE = re.compile(r'\\\[\s*(.*?)\s*\\\]', re.DOTALL)
_INLINE_MATH_RE  = re.compile(r'\\\((.*?)\\\)',        re.DOTALL)

def _fix_latex(text):
    text = _DISPLAY_MATH_RE.sub(lambda m: f'\n$$\n{m.group(1).strip()}\n$$\n', text)
    text = _INLINE_MATH_RE.sub( lambda m: f'${m.group(1)}$',                   text)
    return text
```

The conversion runs after `st.write_stream()` returns (the streaming display shows raw delimiters; the DONE-stage tabs show rendered math).
