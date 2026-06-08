"""Summaries and Flashcards — fully local lecture-notes summariser (Streamlit entry point).

App shell: a persistent sidebar (New summary / Library / status) drives a single
main canvas that swaps on `st.session_state.stage`:
  idle    → upload zone
  running → extract (vision) → summarise (text), with a live progress view
  done    → result header + Summary / Flashcards tabs

Models, depth, and level are fixed (see config); the UI exposes no knobs for them.
"""

import re

import streamlit as st
from ollama import Client

from summariesandflashcards import ollama_client, ingest, summarize, flashcards
from summariesandflashcards.config import SUPPORTED_EXTENSIONS, DEFAULT_MODEL, TEXT_MODEL, OLLAMA_HOST
from summariesandflashcards.ollama_client import is_vision_model
from summariesandflashcards.history import (
    start_run, finish_run, delete_run, clear_stale_runs, save_flashcards, load_history,
)

# ── Constants ──────────────────────────────────────────────────────────────────
_SUMMARY_HEIGHT = 520
_CARD_HEIGHT = 420
_SECTIONS_SHOWN = 5
_DEPTH = "In-depth"
_LEVEL = "Beginner"

_RESULT_KEYS = (
    "file_data", "last_summary", "group_labels",
    "run_id", "flashcards", "flashcards_apkg", "gen_flashcards",
)

_DISPLAY_MATH_RE = re.compile(r"\\\[\s*(.*?)\s*\\\]", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\\\((.*?)\\\)", re.DOTALL)

# App CSS — the only injected styling. Pins the sidebar to viewport height with a flex-1
# scrollable Library, makes the Library items proper truncating menu rows, and turns the
# Download popover into a flat dropdown menu. Selectors use stable data-testids + `.st-key-`
# container classes (from st.container(key=...)).
_APP_CSS = """
<style>
/* sidebar fills the viewport and does NOT scroll itself — the Library handles overflow */
[data-testid="stSidebar"] [data-testid="stSidebarContent"] { height: 100%; overflow: hidden; }
[data-testid="stSidebarUserContent"] { height: 100%; }
[data-testid="stSidebarUserContent"] > div { height: 100%; }
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}
[data-testid="stSidebar"] hr { margin: 0.4rem 0; }
/* match the gap above LIBRARY to the button↔separator gap (caption ships margin-top:0) */
.st-key-library_label { margin-top: 1rem; }
[data-testid="stLayoutWrapper"]:has(> .st-key-library_scroll) {
    flex: 1 1 auto;
    min-height: 0;
}
/* Library fills remaining space and scrolls, with the scroll indicator hidden */
.st-key-library_scroll { height: 100%; overflow-y: auto; scrollbar-width: none; gap: 0; }
.st-key-library_scroll::-webkit-scrollbar { display: none; }

/* Library items: borderless full-width rows, left-aligned, single line, ellipsis */
.st-key-library_scroll button {
    justify-content: flex-start;
    text-align: left;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
}
.st-key-library_scroll button:hover { background: #f0efed !important; }
.st-key-lib_active button { background: #e8e7e4 !important; }  /* active run */
.st-key-library_scroll button > div,
.st-key-library_scroll button > div > span {
    justify-content: flex-start;
    width: 100%;
    min-width: 0;
}
.st-key-library_scroll button [data-testid="stMarkdownContainer"] { min-width: 0; max-width: 100%; }
.st-key-library_scroll button p {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}

/* Download popover → flat dropdown menu: tight body, full-bleed borderless rows.
   The popover body already clips to its radius, so the rows need no radius. */
[data-testid="stPopoverBody"] { padding: 0; }
.st-key-dl_menu { gap: 0; }
.st-key-dl_menu button {
    border: none !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    justify-content: flex-start;
    text-align: left;
    padding: 0.4rem 0.85rem;
}
.st-key-dl_menu button > div,
.st-key-dl_menu button > div > span { justify-content: flex-start; width: 100%; }
.st-key-dl_menu button:hover { background: #f0efed !important; }
</style>
"""


# ── Small helpers ────────────────────────────────────────────────────────────
def _fix_latex(text: str) -> str:
    r"""Convert \[...\] and \(...\) to $$...$$ and $...$ for Streamlit KaTeX."""
    text = _DISPLAY_MATH_RE.sub(lambda m: f"\n$$\n{m.group(1).strip()}\n$$\n", text)
    text = _INLINE_MATH_RE.sub(lambda m: f"${m.group(1)}$", text)
    return text


def _natural_key(name: str) -> list:
    return [
        (0, int(p)) if p.isdigit() else (1, p.lower())
        for p in re.split(r"(\d+)", name)
    ]


def _reset() -> None:
    for k in _RESULT_KEYS:
        st.session_state.pop(k, None)
    st.session_state.stage = "idle"


def _files_label(files: list[str]) -> str:
    head = files[0]
    return head if len(files) == 1 else f"{head}  +{len(files) - 1}"


def _require_ready() -> list[str]:
    """Stop the app with guidance unless Ollama is up and both models are present."""
    if not ollama_client.is_up():
        st.error("**Ollama is not running.** Start it with:\n```\nollama serve\n```\nThen refresh.")
        st.stop()
    models = ollama_client.list_models()
    missing = [m for m in (DEFAULT_MODEL, TEXT_MODEL) if m not in models]
    if missing:
        pulls = "\n".join(f"ollama pull {m}" for m in missing)
        names = ", ".join(f"`{m}`" for m in missing)
        st.error(
            f"**Required model(s) not installed:** {names}.\n\n"
            f"Pull them with:\n```\n{pulls}\n```\nThen refresh."
        )
        st.stop()
    return models


# ── Sidebar (persistent shell) ───────────────────────────────────────────────
def render_sidebar() -> None:
    # Lock navigation while a run is working, so the user can't leave the live
    # view and get stuck unable to return (the pipeline is synchronous).
    busy = bool(st.session_state.get("stage") == "running" or st.session_state.get("gen_flashcards"))
    with st.sidebar:
        st.markdown("## Summaries and Flashcards")

        if st.button("＋  New summary", use_container_width=True, disabled=busy):
            _reset()
            st.rerun()

        st.divider()
        with st.container(key="library_label"):
            st.caption("LIBRARY")
        with st.container(key="library_scroll"):
            runs = load_history()
            if not runs:
                st.caption("No runs yet.")
            active = st.session_state.get("run_id")
            for i, run in enumerate(runs):
                is_active = bool(run.get("id")) and run.get("id") == active
                running = not run.get("summary")  # placeholder from start_run
                label = _files_label(run["files"])
                if running:
                    # The current in-progress run — shown, not navigable.
                    st.button(
                        f"{label}  ·  …", key=f"lib_{i}",
                        use_container_width=True, disabled=True,
                    )
                elif st.button(
                    label,
                    key="lib_active" if is_active else f"lib_{i}",
                    use_container_width=True, disabled=busy,
                ):
                    _load_run(run)
                    st.rerun()

        st.caption(f"{DEFAULT_MODEL} · {TEXT_MODEL}")


def _load_run(run: dict) -> None:
    st.session_state.file_data = [{"name": f, "bytes": b""} for f in run["files"]]
    st.session_state.last_summary = run["summary"]
    st.session_state.group_labels = run.get("group_labels", [])
    st.session_state.run_id = run.get("id", "")
    saved = run.get("flashcards", [])
    st.session_state.flashcards = [(c["q"], c["a"]) for c in saved]
    st.session_state.flashcards_apkg = (
        flashcards.build_apkg(st.session_state.flashcards) if saved else b""
    )
    st.session_state.stage = "done"


# ══════════════════════════════════════════════════════════════════════════════
# IDLE — upload zone
# ══════════════════════════════════════════════════════════════════════════════
def render_idle() -> None:
    st.subheader("New summary")
    st.caption("Drop your notes — PDF, DOCX, PPTX, and more — for a summary and flashcards.")
    uploaded = st.file_uploader(
        "notes", type=SUPPORTED_EXTENSIONS,
        accept_multiple_files=True, label_visibility="collapsed",
    )
    if uploaded and st.button("Summarise", type="primary", use_container_width=True):
        ordered = sorted(uploaded, key=lambda f: _natural_key(f.name))
        st.session_state.file_data = [
            {"name": f.name, "bytes": f.getvalue()} for f in ordered
        ]
        # Register the run immediately so it shows in the Library right away,
        # then fill it in when the pipeline finishes (Claude-Code-style).
        st.session_state.run_id = start_run(
            [d["name"] for d in st.session_state.file_data], DEFAULT_MODEL, _DEPTH, _LEVEL
        )
        st.session_state.stage = "running"
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# RUNNING — live pipeline
# ══════════════════════════════════════════════════════════════════════════════
class _ProgressView:
    """Live, in-place view of the pipeline's segment/skim/group phases."""

    def __init__(self) -> None:
        self._files_ph = st.empty()
        self._sections_ph = st.empty()
        self._groups_ph = st.empty()
        self._files: list[tuple[str, int]] = []
        self._sections: list[tuple[str, str]] = []

    def on_step(self, event: str, data) -> None:
        if event == "segment":
            fi, n_files, name, n_sec = data
            self._files.append((name, n_sec))
            self._draw_files(collapsed=(fi == n_files - 1))
        elif event == "section":
            i, n, title, label = data
            self._sections.append((title, label))
            self._draw_sections(collapsed=(i == n - 1))
        elif event == "groups":
            self._draw_sections(collapsed=True)
            self._draw_groups(data)
            st.session_state.group_labels = [g[0][0][:40] for g in data]
        elif event == "written_labels":
            st.session_state.group_labels = data

    def _draw_files(self, collapsed: bool) -> None:
        with self._files_ph.container():
            with st.expander(f"Files — {len(self._files)} processed", expanded=not collapsed):
                for name, nsec in self._files:
                    st.markdown(f"✓ &nbsp;**{name}** — {nsec} section{'s' * (nsec != 1)}")

    def _draw_sections(self, collapsed: bool) -> None:
        n = len(self._sections)
        shown = self._sections[-_SECTIONS_SHOWN:]
        with self._sections_ph.container():
            with st.expander(f"Sections — {n} labelled", expanded=not collapsed):
                if n - len(shown) > 0:
                    st.caption(f"↑ {n - len(shown)} more above")
                for title, label in shown:
                    st.markdown(f"✓ &nbsp;**{title}** — {label}")

    def _draw_groups(self, groups: list) -> None:
        with self._groups_ph.container():
            with st.expander(f"Groups — {len(groups)} topics", expanded=False):
                for j, group in enumerate(groups):
                    titles = " · ".join(t for t, _, _, _ in group)
                    st.markdown(f"`{j + 1}` &nbsp;{titles}")


def _extract(file_data, vision_enabled, vision_client, progress) -> dict[str, str]:
    extracted: dict[str, str] = {}
    n_files = len(file_data)
    for i, d in enumerate(file_data):
        base, rng = i / n_files * 0.05, 1 / n_files * 0.05
        progress.progress(base, text=f"Extracting {d['name']}…")

        def on_page(idx, total, _d=d, _b=base, _r=rng):
            progress.progress(
                min(_b + _r * (idx + 1) / total, _b + _r),
                text=f"Extracting page {idx + 1} of {total} from {_d['name']}…",
            )

        try:
            key = f"File {i + 1} of {n_files}: {d['name']}"
            extracted[key] = ingest.extract_text(
                d["name"], d["bytes"],
                vision_model=DEFAULT_MODEL if vision_enabled else "",
                client=vision_client, on_page=on_page,
            )
        except Exception as exc:
            st.warning(f"Could not extract **{d['name']}**: {exc}")
    return extracted


def render_running(models: list[str]) -> None:
    file_data = st.session_state.file_data
    st.subheader("Summarising")
    st.caption(_files_label([d["name"] for d in file_data]))
    progress = st.progress(0.0, text="Starting…")

    vision_enabled = is_vision_model(DEFAULT_MODEL)
    vision_client = Client(host=OLLAMA_HOST) if vision_enabled else None
    text_model = TEXT_MODEL if (vision_enabled and TEXT_MODEL in models) else DEFAULT_MODEL

    view = _ProgressView()
    extracted = _extract(file_data, vision_enabled, vision_client, progress)
    if not extracted:
        delete_run(st.session_state.get("run_id", ""))  # no orphan "running" entry
        st.error("No text could be extracted from the uploaded files.")
        if st.button("↩ Start over"):
            _reset()
            st.rerun()
        st.stop()

    combined = "\n\n---\n\n".join(f"# {name}\n\n{text}" for name, text in extracted.items())

    # Free the vision model before the text model loads — keeps peak RAM ~max, not sum.
    if vision_client and text_model != DEFAULT_MODEL:
        try:
            vision_client.chat(model=DEFAULT_MODEL, messages=[], keep_alive=0)
        except Exception:
            pass

    stream = summarize.summarize_mapreduce(
        combined, text_model, _DEPTH, _LEVEL,
        on_progress=lambda msg, pct: progress.progress(pct, text=msg),
        on_step=view.on_step,
    )
    st.markdown("**Summary**")
    with st.container(height=_SUMMARY_HEIGHT, border=True, autoscroll=True):
        result = st.write_stream(stream)

    summary = _fix_latex(result if isinstance(result, str) else "".join(result))
    progress.empty()

    st.session_state.last_summary = summary
    st.session_state.pop("flashcards", None)
    st.session_state.pop("flashcards_apkg", None)
    finish_run(
        st.session_state.get("run_id", ""), summary,
        st.session_state.get("group_labels", []),
    )
    st.session_state.stage = "done"
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# DONE — result canvas
# ══════════════════════════════════════════════════════════════════════════════
def render_done() -> None:
    summary = st.session_state.last_summary
    files = [d["name"] for d in st.session_state.file_data]
    parts = [p.strip() for p in summary.split("\n\n---\n\n") if p.strip()]

    head, actions = st.columns([5, 1], vertical_alignment="center")
    with head:
        st.subheader(_files_label(files))
        src = f" · {len(files)} sources" if len(files) > 1 else ""
        st.caption(f"AI-generated summary{src}")
    with actions:
        with st.popover("Download", use_container_width=True):
            with st.container(key="dl_menu"):
                st.download_button(
                    "Markdown (.md)", data=summary, file_name="summary.md",
                    mime="text/markdown", on_click="ignore", use_container_width=True,
                )
                st.download_button(
                    "Plain text (.txt)", data=summary, file_name="summary.txt",
                    mime="text/plain", on_click="ignore", use_container_width=True,
                )

    tab_summary, tab_cards = st.tabs(["Summary", "Flashcards"])
    with tab_summary:
        _render_summary(parts, summary, st.session_state.get("group_labels", []))
    with tab_cards:
        _render_flashcards(parts)


def _render_summary(parts: list[str], summary: str, labels: list[str]) -> None:
    if len(parts) <= 1:
        st.markdown(summary)
        return

    names = [
        labels[i] if i < len(labels) and labels[i] else f"Part {i + 1}"
        for i in range(len(parts))
    ]
    idx = st.selectbox(
        "Topic", range(len(names)),
        format_func=lambda i: f"{i + 1}.  {names[i]}",
        label_visibility="collapsed",
    )
    st.markdown(parts[idx])


def _render_flashcards(parts: list[str]) -> None:
    deck = list(st.session_state.get("flashcards") or [])

    if deck:
        st.iframe(flashcards.cards_widget_html(deck), height=_CARD_HEIGHT)
        st.download_button(
            "Download deck (.apkg)",
            data=st.session_state.get("flashcards_apkg", b""),
            file_name="flashcards.apkg", mime="application/octet-stream",
            on_click="ignore", use_container_width=True,
        )
        return

    # Two-phase so the sidebar locks before the (blocking) generation: the click
    # sets a flag and reruns; the rerun disables nav, then this branch generates.
    if st.session_state.get("gen_flashcards"):
        with st.spinner("Generating flashcards…"):
            deck = flashcards.generate_cards(parts)
        st.session_state.flashcards = deck
        st.session_state.flashcards_apkg = flashcards.build_apkg(deck) if deck else b""
        save_flashcards(st.session_state.get("run_id", ""), deck)
        st.session_state.pop("gen_flashcards", None)
        if deck:
            st.rerun()
        else:
            st.warning("Couldn't generate flashcards from this summary.")
        return

    if st.button("Generate flashcards", type="primary", use_container_width=True):
        st.session_state.gen_flashcards = True
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Entry
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    st.set_page_config(
        page_title="Summaries and Flashcards", page_icon="📄",
        layout="centered", initial_sidebar_state="expanded",
    )
    models = _require_ready()
    st.session_state.setdefault("stage", "idle")

    # Once per session, before this session starts its own run: drop in-progress
    # placeholders orphaned by a previously-killed process.
    if not st.session_state.get("_swept"):
        clear_stale_runs()
        st.session_state["_swept"] = True

    st.markdown(_APP_CSS, unsafe_allow_html=True)
    render_sidebar()

    stage = st.session_state.stage
    if stage == "running":
        render_running(models)
    elif stage == "done":
        render_done()
    else:
        render_idle()


main()
