import streamlit as st
from summariesandflashcards import ollama_client, ingest
from summariesandflashcards.config import SUPPORTED_EXTENSIONS, DEFAULT_MODEL
from summariesandflashcards.prompts import DEPTH_OPTIONS, auto_depth, PROFICIENCY_OPTIONS
from summariesandflashcards import summarize

st.set_page_config(page_title="Summaries and Flashcards", page_icon="📄", layout="wide")
st.title("📄 Summaries and Flashcards")
st.caption("AI-powered lecture notes summariser — fully local, no internet required.")

# ── Ollama health check ───────────────────────────────────────────────────────
if not ollama_client.is_up():
    st.error(
        "**Ollama is not running.** Start it with:\n\n"
        "```\nollama serve\n```\n\n"
        "Then refresh this page."
    )
    st.stop()

models = ollama_client.list_models()
if not models:
    st.error(
        "**No models installed.** Pull the default model with:\n\n"
        f"```\nollama pull {DEFAULT_MODEL}\n```\n\n"
        "Then refresh this page."
    )
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    default_idx = models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0
    selected_model = st.selectbox("Model", models, index=default_idx)
    st.caption("Ollama server: `localhost:11434` ✅")

# ── File upload ───────────────────────────────────────────────────────────────
st.subheader("Upload your notes")
uploaded_files = st.file_uploader(
    "Drag and drop files here",
    type=SUPPORTED_EXTENSIONS,
    accept_multiple_files=True,
    help=f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
)

if not uploaded_files:
    st.info("Upload one or more files to get started.")
    st.stop()

# ── Extract text ──────────────────────────────────────────────────────────────
extracted: dict[str, str] = {}

for f in uploaded_files:
    with st.spinner(f"Extracting `{f.name}`…"):
        try:
            text = ingest.extract_text(f.name, f.getvalue())
            extracted[f.name] = text
        except Exception as exc:
            st.warning(f"Could not extract **{f.name}**: {exc}")

if not extracted:
    st.stop()

# ── Text preview ──────────────────────────────────────────────────────────────
st.subheader("Extracted text preview")
for name, text in extracted.items():
    word_count = len(text.split())
    with st.expander(f"**{name}** — {word_count:,} words", expanded=False):
        st.text_area(
            label=name,
            value=text[:4000] + ("…" if len(text) > 4000 else ""),
            height=300,
            disabled=True,
            label_visibility="collapsed",
        )

st.divider()

# ── Summarise ─────────────────────────────────────────────────────────────────
st.subheader("Summary")

# Combine all extracted files into one body of text.
# Files are labelled with their position so the model understands course ordering.
total_files = len(extracted)
combined_text = "\n\n---\n\n".join(
    f"# File {i} of {total_files}: {name}\n\n{text}"
    for i, (name, text) in enumerate(extracted.items(), 1)
)

# Auto-detect depth from total word count; let user override in sidebar
total_words = len(combined_text.split())
detected_depth = auto_depth(total_words)

with st.sidebar:
    st.divider()
    summary_depth = st.radio(
        "Summary depth",
        DEPTH_OPTIONS,
        index=DEPTH_OPTIONS.index(detected_depth),
        help="Auto-selected based on document length. Change if you prefer a different style.",
    )
    st.caption(f"Auto-detected from {total_words:,} words")

    st.divider()
    proficiency = st.radio(
        "Your level in this subject",
        PROFICIENCY_OPTIONS,
        index=PROFICIENCY_OPTIONS.index("Intermediate"),
        help=(
            "Beginner: terms are defined and re-explained throughout. "
            "Intermediate: advanced terms defined once. "
            "Expert: full technical language, no definitions."
        ),
    )

use_mapreduce = summarize.needs_mapreduce(combined_text)
if use_mapreduce:
    chunks = summarize.chunk_text(combined_text)
    st.info(
        f"Document has **{len(chunks)} sections** — each will be summarised independently "
        "then merged for better accuracy."
    )

if st.button("✨ Summarise", type="primary", use_container_width=True):
    try:
        if use_mapreduce:
            progress_bar = st.progress(0.0, text="Starting…")

            def on_progress(msg: str, pct: float) -> None:
                progress_bar.progress(pct, text=msg)

            summary = st.write_stream(
                summarize.summarize_mapreduce(combined_text, selected_model, summary_depth, proficiency, on_progress)
            )
            progress_bar.empty()
        else:
            with st.spinner(f"Summarising with **{selected_model}**…"):
                summary = st.write_stream(
                    summarize.summarize_stream(combined_text, selected_model, summary_depth, proficiency)
                )
        st.session_state["last_summary"] = summary
    except Exception as exc:
        st.error(f"Summarisation failed: {exc}")

elif "last_summary" in st.session_state:
    st.markdown(st.session_state["last_summary"])

if "last_summary" in st.session_state:
    st.download_button(
        label="⬇ Download summary (.txt)",
        data=st.session_state["last_summary"],
        file_name="summary.txt",
        mime="text/plain",
    )
