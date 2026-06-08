"""Summaries and Flashcards — fully local lecture-notes summariser (basic Streamlit app).

Upload notes → summarise → optional Anki flashcards. Models/depth/level are fixed
(see summariesandflashcards/config.py). The summarisation engine (gated pipeline, vision
extraction, flashcard generation) lives in the summariesandflashcards package.
"""

import re

import streamlit as st
from ollama import Client

from summariesandflashcards import ollama_client, ingest, summarize, flashcards
from summariesandflashcards.config import SUPPORTED_EXTENSIONS, DEFAULT_MODEL, TEXT_MODEL, OLLAMA_HOST
from summariesandflashcards.ollama_client import is_vision_model

_DEPTH = "In-depth"
_LEVEL = "Beginner"

_DISPLAY_MATH_RE = re.compile(r"\\\[\s*(.*?)\s*\\\]", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\\\((.*?)\\\)", re.DOTALL)


def _fix_latex(text: str) -> str:
    r"""Convert \[...\] / \(...\) to $$...$$ / $...$ so st.markdown renders KaTeX."""
    text = _DISPLAY_MATH_RE.sub(lambda m: f"\n$$\n{m.group(1).strip()}\n$$\n", text)
    return _INLINE_MATH_RE.sub(lambda m: f"${m.group(1)}$", text)


st.set_page_config(page_title="Summaries and Flashcards", page_icon="📄")
st.title("Summaries and Flashcards")
st.caption("Local lecture-notes summariser.")

# ── Health check ──────────────────────────────────────────────────────────────
if not ollama_client.is_up():
    st.error("Ollama is not running. Start it with `ollama serve`, then refresh.")
    st.stop()
models = ollama_client.list_models()
missing = [m for m in (DEFAULT_MODEL, TEXT_MODEL) if m not in models]
if missing:
    st.error("Required model(s) not installed: " + ", ".join(f"`{m}`" for m in missing)
             + ". Pull with `ollama pull <name>`, then refresh.")
    st.stop()

# ── Upload + summarise ────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload notes (PDF, DOCX, PPTX, …)",
    type=SUPPORTED_EXTENSIONS, accept_multiple_files=True,
)

if uploaded and st.button("Summarise", type="primary"):
    vision = is_vision_model(DEFAULT_MODEL)
    vision_client = Client(host=OLLAMA_HOST) if vision else None
    text_model = TEXT_MODEL if (vision and TEXT_MODEL in models) else DEFAULT_MODEL

    extracted: dict[str, str] = {}
    with st.spinner("Extracting text…"):
        for i, f in enumerate(uploaded):
            try:
                extracted[f"File {i + 1} of {len(uploaded)}: {f.name}"] = ingest.extract_text(
                    f.name, f.getvalue(),
                    vision_model=DEFAULT_MODEL if vision else "", client=vision_client,
                )
            except Exception as exc:
                st.warning(f"Could not extract {f.name}: {exc}")

    if not extracted:
        st.error("No text could be extracted from the uploaded files.")
        st.stop()

    combined = "\n\n---\n\n".join(f"# {name}\n\n{text}" for name, text in extracted.items())
    if vision_client and text_model != DEFAULT_MODEL:
        try:  # free the vision model before the text model loads (low-RAM friendly)
            vision_client.chat(model=DEFAULT_MODEL, messages=[], keep_alive=0)
        except Exception:
            pass

    with st.spinner("Summarising…"):
        summary = "".join(summarize.summarize_mapreduce(combined, text_model, _DEPTH, _LEVEL))
    st.session_state.summary = _fix_latex(summary)
    st.session_state.pop("cards", None)

# ── Results ───────────────────────────────────────────────────────────────────
if "summary" in st.session_state:
    summary = st.session_state.summary

    st.subheader("Summary")
    st.markdown(summary)
    st.download_button("Download summary (.md)", summary, "summary.md", "text/markdown")

    st.subheader("Flashcards")
    if st.button("Generate flashcards"):
        parts = [p.strip() for p in summary.split("\n\n---\n\n") if p.strip()]
        with st.spinner("Generating flashcards…"):
            st.session_state.cards = flashcards.generate_cards(parts)

    cards = st.session_state.get("cards")
    if cards:
        for q, a in cards:
            with st.expander(q):
                st.markdown(a)
        st.download_button(
            "Download deck (.apkg)", flashcards.build_apkg(cards),
            "flashcards.apkg", "application/octet-stream",
        )
    elif cards is not None:
        st.warning("Couldn't generate flashcards from this summary.")
