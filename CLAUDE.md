# Global Preferences

## Git
Before checking out a different branch, always `git stash` first. After finishing work on the other branch, return to the original branch and run `git stash pop`.

## CLAUDE.md
Keep `CLAUDE.md` up to date. Whenever a change affects how the project is built, deployed, structured, or understood, update the project's `CLAUDE.md` to reflect it — without being asked. If no `CLAUDE.md` exists and the project is non-trivial, run `/init` to create one.

## Research rule — NEVER skip this

The goal of this entire ruleset is simple: **never rely on the knowledge base. Ever.** Training data is guaranteed to be stale, wrong, or deprecated — libraries change, APIs are removed, bugs get filed, and the knowledge base always lags behind. All facts about libraries, APIs, errors, and platform behaviour must come from live sources fetched in the current session.

**Before writing any code that uses a library API** — fetch the official docs. No guessing. No assuming. Docs first, code after.

**Before answering any question about a library, API, or error** — web-search the issue first, then fetch the relevant page. Even simple factual questions ("does X support Y?", "why does Z fail?") must be answered from fetched content, not memory. A wrong confident answer is worse than saying "let me check."

**Before diagnosing any build error, bundler error, or runtime crash** — search the web for the exact error message + relevant package names. Check GitHub issues and official docs before proposing a fix.

## Always propose before implementing — NEVER skip this

**Never start writing or editing code without first telling the user what you plan to do and getting confirmation.**
State the approach, the files that will change, and any tradeoffs. Wait for the user to say yes before touching any code.
This applies to every non-trivial change. The only exception is a fix so small and obvious that it fits in one sentence and has no alternatives.

## Project working rules — Summaries and Flashcards

- **Faithfulness over completeness.** The app's whole value is summaries that never
  invent facts. When editing prompts, the pipeline, or flashcards: use only what's in
  the source; never add outside knowledge, definitions, or examples. Preserve the
  anti-hallucination gates (main/standard). Validate changes against a real lecture
  file and compare output to the source before calling it done.
- **Don't parallelize Ollama for speed.** It serializes requests on a single host
  (~1.0x from concurrency, measured). The levers for extraction speed are image
  downscaling (`VISION_MAX_PX`), skipping small/decorative images, skipping vision on
  text-rich slides, and capping `num_predict` — not threads or async.
- **Respect Streamlit's rerun model.** Any widget interaction reruns and ABORTS the
  in-flight script. For downloads during/after a run use `on_click="ignore"`; lock
  navigation while a run is working; prefer client-side widgets (`st.expander`) that
  don't rerun. Verify a long run can't be interrupted by a stray click.
- **Manage model RAM explicitly (main/standard).** Extract with the vision model,
  unload it (`keep_alive=0`) before the text model loads, so peak RAM ≈ the larger
  model, not the sum. lite uses one user-chosen model for both phases.
- **genanki invariants.** `Package.write_to_file` takes a path only (temp-file
  roundtrip). The fixed `_MODEL_ID`/`_DECK_ID` must never change or re-imported decks
  break in Anki.
- **Keep the three branches distinct.** main = full deluxe UI; standard = full engine
  + basic UI; lite = single-pass + model picker + basic UI. When changing shared
  engine code, decide whether every branch needs it; don't bleed UI features across.
- **Keep deps honest.** Adding/removing an import means updating `requirements.txt`,
  `ATTRIBUTIONS.md`, and the README tables together. Verify every licence from
  installed metadata (`importlib.metadata`), never from memory. Never list a dep you
  don't import.
- **Never track runtime/junk.** `history.json`, `logs/`, `__pycache__`, `debug_*.txt`
  are gitignored — don't commit them.
- **Keep the app's own look.** The theme is minimal monochrome (white, near-black,
  Georgia headings) in `.streamlit/config.toml`; evolve that. Never apply the Matsuo
  Kengo portfolio brand (`matsuokengo-design`) here: the owner treats this as its own
  tool, not a branded product.
