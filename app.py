"""Summaries and Flashcards (lite) — fully local lecture-notes summariser (basic Streamlit app).

Upload notes → summarise → optional Anki flashcards. You pick one installed model:
a vision model (e.g. qwen2.5vl:3b) reads equations/diagrams/images in slides, a
text-only model is lighter but skips image content. That single model does both the
extraction and the summary. The engine lives in the summariesandflashcards package.
"""

import re

import streamlit as st
from ollama import Client

from summariesandflashcards import ollama_client, ingest, summarize, flashcards
from summariesandflashcards.config import SUPPORTED_EXTENSIONS, DEFAULT_MODEL, OLLAMA_HOST
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
st.caption("Lecture-notes summariser.")

# ── Health check ──────────────────────────────────────────────────────────────
if not ollama_client.is_up():
    st.error("Ollama is not running. Start it with `ollama serve`, then refresh.")
    st.stop()
models = ollama_client.list_models()
if not models:
    st.error("No Ollama models installed. Pull one with `ollama pull qwen2.5vl:3b`, then refresh.")
    st.stop()

# ── Model + upload ────────────────────────────────────────────────────────────
default_idx = models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0
model = st.selectbox("Model", models, index=default_idx)
if is_vision_model(model):
    st.caption("Vision model — reads equations, diagrams, and images in slides/pages.")
else:
    st.caption("Text-only model — lighter, but image-only content is skipped.")

uploaded = st.file_uploader(
    "Upload notes (PDF, DOCX, PPTX, …)",
    type=SUPPORTED_EXTENSIONS, accept_multiple_files=True,
)

if uploaded and st.button("Summarise", type="primary"):
    vision = is_vision_model(model)
    vision_client = Client(host=OLLAMA_HOST) if vision else None

    extracted: dict[str, str] = {}
    with st.spinner("Extracting text…"):
        for i, f in enumerate(uploaded):
            try:
                extracted[f"File {i + 1} of {len(uploaded)}: {f.name}"] = ingest.extract_text(
                    f.name, f.getvalue(),
                    vision_model=model if vision else "", client=vision_client,
                )
            except Exception as exc:
                st.warning(f"Could not extract {f.name}: {exc}")

    if not extracted:
        st.error("No text could be extracted from the uploaded files.")
        st.stop()

    combined = "\n\n---\n\n".join(f"# {name}\n\n{text}" for name, text in extracted.items())

    st.subheader("Summary")
    summary = _fix_latex(
        st.write_stream(summarize.summarize_stream(combined, model, _DEPTH, _LEVEL))
    )
    st.session_state.summary = summary
    st.session_state.model = model
    st.session_state.pop("cards", None)
    # The stream above is transient; rerun so the Results block below is the single
    # source of truth (avoids rendering the summary twice in this pass).
    st.rerun()

# ── Results ───────────────────────────────────────────────────────────────────
if "summary" in st.session_state:
    summary = st.session_state.summary

    st.subheader("Summary")
    st.markdown(summary)
    st.download_button("Download summary (.md)", summary, "summary.md", "text/markdown")

    st.subheader("Flashcards")
    if st.button("Generate flashcards"):
        parts = [p.strip() for p in summary.split("\n\n") if p.strip()]
        with st.spinner("Generating flashcards…"):
            st.session_state.cards = flashcards.generate_cards(
                parts, model=st.session_state.get("model", model),
            )

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
