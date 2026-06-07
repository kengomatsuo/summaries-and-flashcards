import re
import streamlit as st
from ollama import Client
from summariesandflashcards import ollama_client, ingest
from summariesandflashcards.config import SUPPORTED_EXTENSIONS, DEFAULT_MODEL, OLLAMA_HOST
from summariesandflashcards.prompts import DEPTH_OPTIONS, PROFICIENCY_OPTIONS
from summariesandflashcards import summarize
from summariesandflashcards.ollama_client import is_vision_model

_SUMMARY_HEIGHT = 500
_SECTIONS_SHOWN = 5

_DISPLAY_MATH_RE = re.compile(r'\\\[\s*(.*?)\s*\\\]', re.DOTALL)
_INLINE_MATH_RE = re.compile(r'\\\((.*?)\\\)', re.DOTALL)


def _fix_latex(text: str) -> str:
    """Convert \[...\] and \(...\) to $$...$$ and $...$ for Streamlit KaTeX."""
    text = _DISPLAY_MATH_RE.sub(lambda m: f'\n$$\n{m.group(1).strip()}\n$$\n', text)
    text = _INLINE_MATH_RE.sub(lambda m: f'${m.group(1)}$', text)
    return text


def _natural_key(name: str) -> list:
    return [
        (0, int(p)) if p.isdigit() else (1, p.lower())
        for p in re.split(r'(\d+)', name)
    ]


st.set_page_config(page_title="Summaries and Flashcards", page_icon="📄", layout="centered")

# ── Health check ──────────────────────────────────────────────────────────────
if not ollama_client.is_up():
    st.error(
        "**Ollama is not running.** Start it with:\n```\nollama serve\n```\nThen refresh."
    )
    st.stop()

models = ollama_client.list_models()
if not models:
    st.error(
        f"**No models installed.** Pull one with:\n```\nollama pull {DEFAULT_MODEL}\n```\nThen refresh."
    )
    st.stop()

# ── Session state init ────────────────────────────────────────────────────────
if "stage" not in st.session_state:
    st.session_state.stage = "idle"

# ── Header ────────────────────────────────────────────────────────────────────
st.title("Summaries and Flashcards")
st.caption("Fully local AI lecture notes summariser — no internet required.")

# ══════════════════════════════════════════════════════════════════════════════
# IDLE — upload + configure
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.stage == "idle":
    uploaded_files = st.file_uploader(
        "notes",
        type=SUPPORTED_EXTENSIONS,
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:
        st.divider()
        default_idx = models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0
        # Tag vision-capable models in the dropdown so the user knows what they get
        model_labels = [
            f"{m}  (vision)" if is_vision_model(m) else f"{m}  (text only — faster)"
            for m in models
        ]
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_label = st.selectbox("Model", model_labels, index=default_idx)
            selected_model = models[model_labels.index(selected_label)]
        with col2:
            summary_depth = st.radio("Depth", DEPTH_OPTIONS, index=1)
        with col3:
            proficiency = st.radio("Level", PROFICIENCY_OPTIONS, index=1)

        if st.button("✨ Summarise", type="primary", use_container_width=True):
            sorted_files = sorted(uploaded_files, key=lambda f: _natural_key(f.name))
            st.session_state.file_data = [
                {"name": f.name, "bytes": f.getvalue()} for f in sorted_files
            ]
            st.session_state.selected_model = selected_model
            st.session_state.summary_depth = summary_depth
            st.session_state.proficiency = proficiency
            st.session_state.stage = "running"
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# RUNNING — live pipeline view
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "running":
    file_data: list[dict] = st.session_state.file_data
    model: str = st.session_state.selected_model
    depth: str = st.session_state.summary_depth
    proficiency: str = st.session_state.proficiency

    st.markdown("  ".join(f"`{d['name']}`" for d in file_data))
    progress_bar = st.progress(0.0, text="Starting…")

    # One st.empty() per pipeline step — contents are swapped in/out as steps run
    files_ph = st.empty()
    sections_ph = st.empty()
    groups_ph = st.empty()

    # ── Render helpers ─────────────────────────────────────────────────────────
    files_acc: list[tuple[str, int]] = []
    sections_acc: list[tuple[str, str]] = []

    def _render_files(collapsed: bool = False) -> None:
        n = len(files_acc)
        label = f"Files — {n} processed" if n else "Files"
        with files_ph.container():
            with st.expander(label, expanded=not collapsed):
                for fname, nsec in files_acc:
                    noun = "section" if nsec == 1 else "sections"
                    st.markdown(f"✓ &nbsp;**{fname}** — {nsec} {noun}")

    def _render_sections(collapsed: bool = False) -> None:
        n = len(sections_acc)
        label = f"Sections — {n} labelled" if n else "Sections"
        shown = sections_acc[-_SECTIONS_SHOWN:]
        n_hidden = n - len(shown)
        with sections_ph.container():
            with st.expander(label, expanded=not collapsed):
                if n_hidden > 0:
                    st.caption(f"↑ {n_hidden} more above")
                for title, lbl in shown:
                    st.markdown(f"✓ &nbsp;**{title}** — {lbl}")

    def _render_groups(groups: list) -> None:
        n = len(groups)
        with groups_ph.container():
            with st.expander(f"Groups — {n} topics", expanded=False):
                for j, group in enumerate(groups):
                    titles = " · ".join(t for t, _, _ in group)
                    st.markdown(f"`{j + 1}` &nbsp;{titles}")

    # ── Callbacks ──────────────────────────────────────────────────────────────
    def on_progress(msg: str, pct: float) -> None:
        progress_bar.progress(pct, text=msg)

    def on_step(event: str, data) -> None:
        if event == "segment":
            fi, n_files, file_name, n_sections = data
            files_acc.append((file_name, n_sections))
            _render_files(collapsed=(fi == n_files - 1))
        elif event == "section":
            i, n, title, label = data
            sections_acc.append((title, label))
            _render_sections(collapsed=(i == n - 1))
        elif event == "groups":
            groups: list = data
            _render_sections(collapsed=True)
            _render_groups(groups)
            # Store group labels for DONE stage tabs
            st.session_state.group_labels = [
                (t for t, _, _ in group).__next__()[:40]
                for group in groups
            ]

    # ── Extract ────────────────────────────────────────────────────────────────
    extracted: dict[str, str] = {}
    n_files = len(file_data)
    vision_enabled = is_vision_model(model)
    vision_client = Client(host=OLLAMA_HOST) if vision_enabled else None
    for i, d in enumerate(file_data):
        progress_bar.progress((i / n_files) * 0.05, text=f"Extracting {d['name']}…")
        try:
            extracted[f"File {i + 1} of {n_files}: {d['name']}"] = (
                ingest.extract_text(
                    d["name"], d["bytes"],
                    vision_model=model if vision_enabled else "",
                    client=vision_client,
                )
            )
        except Exception as exc:
            st.warning(f"Could not extract **{d['name']}**: {exc}")

    if not extracted:
        st.error("No text could be extracted from the uploaded files.")
        if st.button("↩ Start over"):
            st.session_state.stage = "idle"
            st.rerun()
        st.stop()

    combined = "\n\n---\n\n".join(
        f"# {name}\n\n{text}" for name, text in extracted.items()
    )

    # ── Run pipeline + stream into fixed-height container ─────────────────────
    stream = summarize.summarize_mapreduce(
        combined, model, depth, proficiency,
        on_progress=on_progress,
        on_step=on_step,
    )

    st.markdown("**Summary**")
    result = st.write_stream(stream)

    summary: str = result if isinstance(result, str) else "".join(result)
    summary = _fix_latex(summary)
    progress_bar.empty()
    st.session_state.last_summary = summary
    st.session_state.stage = "done"
    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# DONE — results
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "done":
    file_data = st.session_state.file_data
    summary: str = st.session_state.last_summary
    group_labels: list[str] = st.session_state.get("group_labels", [])

    col_files, col_reset = st.columns([6, 1])
    with col_files:
        st.markdown("  ".join(f"`{d['name']}`" for d in file_data))
    with col_reset:
        if st.button("↩", help="Start over"):
            for key in [
                "stage", "file_data", "last_summary",
                "selected_model", "summary_depth", "proficiency", "group_labels",
            ]:
                st.session_state.pop(key, None)
            st.rerun()

    st.divider()

    # Split by group separators written during Phase 3
    parts = [p.strip() for p in summary.split("\n\n---\n\n") if p.strip()]

    if len(parts) > 1:
        # Label tabs: use stored first-section title, fall back to "Part N"
        tab_names = []
        for i in range(len(parts)):
            if i < len(group_labels) and group_labels[i]:
                tab_names.append(group_labels[i])
            else:
                tab_names.append(f"Part {i + 1}")

        tabs = st.tabs(tab_names)
        for tab, part in zip(tabs, parts):
            with tab:
                with st.container(height=_SUMMARY_HEIGHT, border=False):
                    st.markdown(part)
    else:
        with st.container(height=_SUMMARY_HEIGHT, border=False):
            st.markdown(summary)

    st.divider()

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "⬇ Download (.md)",
            data=summary,
            file_name="summary.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with dl2:
        st.download_button(
            "⬇ Download (.txt)",
            data=summary,
            file_name="summary.txt",
            mime="text/plain",
            use_container_width=True,
        )
