# Summaries and Flashcards — Design decisions

Rationale behind non-obvious choices. "Why not the obvious thing?"

---

## Dropped LLM segmentation

**What we tried:** An LLM call to identify section headings and split the document into logical chunks before summarising.

**Why it failed:** At 3B scale, the model treated every bullet point, sub-heading, and diagram label as a top-level heading. Results on real lecture PDFs:

- 38 sections from a 5-page handout
- 112 sections from a 40-slide deck
- 109 sections from a 15-slide deck

This made grouping useless (99 groups from one document) and multiplied API call count by 5–10×.

**What replaced it:** Form-feed (`\x0c`) splitting for PDFs and PPTX — PyMuPDF and python-pptx write these at every page/slide boundary, so each section is reliably one slide. For formats without form feeds, paragraph splitting (`\n\n+`) produces blocks that are already roughly slide-sized. No LLM involved in segmentation at all.

---

## PyMuPDF + python-pptx instead of MarkItDown for PDF/PPTX

**Why MarkItDown is kept for everything else:** It handles DOCX, XLSX, HTML, EPUB, and MSG with zero extra dependencies. For text-heavy formats that have no images it is perfectly adequate.

**Why PDF and PPTX need custom handling:**

1. **No per-page/slide control.** MarkItDown converts the whole document to one string. There is no hook to decide "this page needs a vision model call, that one is fine as text."

2. **Equations render as garbage.** PDFs that embed equations as vector text (common in academic slide decks) produce output like `( v = \sqrt { E ρ } )` — garbled character fragments. MarkItDown cannot fix this; PyMuPDF exposes the raw text and a `get_pixmap()` rasteriser. A vision model describing the rasterised image captures the equation correctly.

3. **Embedded images are inaccessible.** PPTX picture shapes are opaque to MarkItDown. python-pptx exposes `shape.image.blob` directly, which can be base64-encoded and sent to the vision model.

---

## Vision model = text model (no separate selector)

The UI has one model dropdown. If the selected model is vision-capable (detected by name pattern), it is used for both text summarisation and image description during ingest.

**Why:** Users should not need to understand the difference between a vision model and a text model to use the app. A single choice is less confusing. The `(vision)` tag in the dropdown makes the capability visible without requiring a separate decision.

**Downside:** A non-vision model produces no image or equation descriptions. Pages that fail the noise-ratio and image checks are still summarised from their (possibly garbled) extracted text. This is the correct degradation — the app still works, it just misses image content.

---

## `num_predict` cap on every LLM call

**Why:** During testing with `AcousticSystems_5th-2.pdf`, a 3B model given a page with noise ratio 0.71 (almost pure math symbols) entered an infinite repetition loop — repeating the same phrase indefinitely. The run had to be killed manually after several minutes.

**Caps applied:**

| Call type | Cap |
|---|---|
| Vision description | `num_predict=1000` |
| Write (summary) | `num_predict=2000` |

These are generous upper bounds. No legitimate description of one slide or summary of one topic group needs more tokens than this. The cap only fires when the model loops.

---

## `noise_ratio > 0.35` as a third vision trigger

**The problem:** Slides with heavy equations (acoustic wave equations, signal processing) have their math typeset as PDF vector text — not raster images. So `page.get_images()` returns 0. And the text passes `_MEANINGFUL_RE` (5-letter word filter) because real English words are mixed in ("velocity", "potential", "source").

**The fix:** Count the fraction of whitespace-separated tokens that are ≤2 characters. Equation-heavy pages have many single-char tokens: `∂`, `ρ`, `=`, `j`, `k`, `t`, numbers, isolated letters from broken fractions. A ratio above 0.35 is a reliable signal.

**Calibration:** AcousticSystems Group 9 scores 0.71. A normal text slide is typically under 0.20. The 0.35 threshold leaves comfortable headroom between the two populations.

---

## Labels are never used as summary input

The Skim phase produces 5-word labels for grouping only. The Write phase always uses the raw section text.

**Why:** A 5-word label is a lossy summary. Using it as the source for the final summary would compound the information loss. The pipeline's advantage over a naive "summarise everything at once" approach is that it can apply `depth` and `proficiency` settings to focused single-topic raw text — not to a chain of telephone-game condensations.

---

## No height container during streaming

`st.container(autoscroll=True)` does not work when child content is produced by `st.write_stream()`. Confirmed by Streamlit GitHub issue #8836: autoscroll fires once on container creation, before any tokens arrive, so the scroll position never moves.

Removing the height wrapper during the RUNNING stage lets the page scroll naturally as tokens stream in. Fixed-height containers are used only in the DONE stage, where all content is present at once and bounded scrolling is appropriate.

---

## LaTeX delimiter post-processing

**Why prompting alone is insufficient:** The write prompt and vision prompt both instruct the model to use `$...$` and `$$...$$`. At 3B scale, models reliably output `\(...\)` and `\[...\]` (standard LaTeX document convention) regardless. Compliance with delimiter format instructions is too inconsistent to rely on.

**The fix:** Two regexes applied after `st.write_stream()` completes, before the summary is stored in session state. The streaming display shows raw delimiters; the DONE-stage tabs show rendered math. This is acceptable — users see the rendered version when reading the final result.

---

## Thin slides are gated in code, not by prompt (anti-hallucination)

**The problem:** A small model (e.g. `qwen2.5vl:3b`) given a near-empty slide and a "be comprehensive" instruction does not stay silent — it fills the void from parametric memory. Observed on a real deck: a slide whose only text was `Result` produced a full sorting-algorithms lecture; `Get target picture` + a Mona Lisa caption produced an image-processing lecture; title slides produced fabricated `ROC/AUC/Naive Bayes/SVM` content. The write prompt *told* the model to skip such slides, but at 3B scale the prohibition loses to the prior to be helpful and complete.

**Why prompting alone is insufficient:** negative instructions ("do not add facts not in the notes", "write nothing for title slides") are unreliable on small models. Proof: every group opened with the exact phrase the prompt forbade (`"The lecture covered…"`).

**The fix:** prevent rather than instruct.
- **Gate A** (`summarize.py`, between Group and Write): drop any group with fewer than `MIN_GROUP_WORDS` *teachable* words — counted per section after stripping the file header, trailing `[Image: …]` captions, and `STEP n OF m` labels. The model is never asked to summarise an empty slide, so it cannot invent one. **Gate A is the sole authority on what gets summarised.**
- **Gate B** (in Write): strip the narration opener deterministically, and detect a *decline* (`SKIP`/`None`/`N/A` or a verbose refusal) purely as a safety net.

**Why the writer no longer decides for itself:** an earlier version asked the writer to reply `SKIP` for contentless sections. At 3B scale the writer's judgment is unreliable in *both* directions: it invented lectures for empty slides (the bug above) *and*, once the prompt was made strict, it wrongly SKIPped terse-but-real slides — a Setup slide listing the dataset, libraries, and accuracy target came back as `SKIP`/`None`, and an Introduction with the real-world applications came back as `SKIP`. Relaxing the SKIP wording did not fix it (the model's instinct beat the instruction). So the SKIP instruction was removed entirely: Gate A (deterministic) decides inclusion, and the write prompt tells the model to *always* restate the notes' specifics in its own words. Gate B's decline-detection remains only to catch a model that refuses anyway. Net effect: every Gate-A-surviving slide is summarised, including setup/intro/conclusion. The residual cost is mild padding on the very thinnest surviving slides under In-depth (the model fills with adjacent-true facts) — far milder than the original wholesale fabrication, and the accepted trade for completeness.

**Caption strip caveat:** image captions are matched from `[Image:` to **end of section**, not to the first `]`, because a caption can itself contain `]` (e.g. an array index `System[n]`). This is safe because `ingest.py` always *appends* captions after a section's text.

**Tradeoff:** image-only / pipeline-diagram decks (e.g. a deepfake "source → analyze → warp → result" sequence carried entirely by pictures) have no teachable *text* and are dropped wholesale. This is faithful — there is nothing in the notes to summarise — but a future "describe visual slides" mode could surface that content explicitly rather than silently.

**Calibration:** title slides in the test corpus run ~8–9 teachable words; pipeline-step labels (`Result`) run 1–3; the thinnest real content slide ran 22. `MIN_GROUP_WORDS = 12` sits in the gap. It is a config knob — raise to drop more aggressively, lower to keep terser slides (at the risk of a one-line definition slide like `F = ma` being dropped).

---

## Separate vision and text models, unloaded between phases

The vision model (`qwen2.5vl:3b`) and a text-only model (`qwen2.5:3b`) are both used per run; there is no in-app model picker.

**Why two models:** a vision (VL) model is a weaker instruction-follower than its text-only sibling of the same parameter count. Side-by-side on the same deck, the VL model summarised acceptably but the text-only sibling was cleaner and more complete. Different *families* react very differently to the strict anti-hallucination prompt: `qwen2.5:3b` complies; `llama3.2:3b` panics and over-refuses real content (it replied "I don't see any lecture theory…" to slides that clearly had some). So the text model is pinned to `qwen2.5:3b`, not left to the user.

**Why unload between phases:** extraction (vision) fully completes before the text phases begin, but Ollama keeps a model resident for 5 min by default, so without intervention both 3B models sit in RAM at once (~5 GB). After extraction, `app.py` unloads the vision model with an empty-`messages` + `keep_alive=0` chat call (returns `done_reason: "unload"`), dropping peak RAM to ~3.2 GB. This matters on low-RAM machines; a 7B writer was rejected for exactly this reason (~7.9 GB peak + swap risk).

**Why no model picker / fixed In-depth + Beginner:** the pipeline is tuned around this specific model pair and prompt. Exposing arbitrary models (the old dropdown) invited the `llama3.2`-style failure. Depth/proficiency were collapsed to In-depth/Beginner because that is the intended use (study notes for a newcomer) and fewer knobs means fewer ways to get a bad result. The instruction text still exists in `prompts.py`; only the UI was removed.

---

## `temperature: 0` on all pipeline calls

Every LLM call — vision describe, skim, group adjacency, write — runs at `temperature: 0`.

**Why:** summarisation must stay faithful to a source, so sampling randomness is pure downside. At the model default (~0.7) repeated runs drifted, dropped detail, and occasionally emitted junk tokens (a literal `None` as a section "summary"). At `temperature: 0` the pipeline is deterministic — identical input produces an identical summary — which also makes the gates above debuggable. There is no creativity benefit to trade away for this task.
