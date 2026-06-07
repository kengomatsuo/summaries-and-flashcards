PROFICIENCY_OPTIONS = ["Beginner", "Intermediate", "Expert"]

PROFICIENCY_INSTRUCTIONS = {
    "Beginner": (
        "Write for a reader who is new to this subject. "
        "Define every technical term the first time it appears, and briefly re-state its meaning each time it recurs. "
        "Assume the reader only knows concepts one level below this course. "
        "Use plain language and everyday analogies wherever possible."
    ),
    "Intermediate": (
        "Assume the reader has standard course prerequisites. "
        "Define advanced or niche terms once, but skip definitions for common subject vocabulary."
    ),
    "Expert": (
        "Write for a reader already fluent in this field. "
        "Use technical language freely. No definitions or analogies needed."
    ),
}

_PREAMBLE = (
    "You are a lecture summariser. Your ONLY job is to summarise the theory and concepts taught.\n\n"
    "STRICT RULES:\n"
    "1. ONLY include information explicitly present in the provided notes. Do NOT add background knowledge.\n"
    "2. Cover ALL topics — do not skip any section.\n"
    "3. If files are labelled 'File 1 of N', 'File 2 of N', etc., treat them in that order — earlier files introduce concepts later files build on.\n"
    "4. Write about the theory: concepts, definitions, algorithms, methods.\n"
    "5. When a section contains exercises or practice problems, discuss what they are practising and reference the relevant theory or formula. Do NOT solve them or show step-by-step calculations.\n"
    "6. NEVER write 'Final answer', worked calculations, or step-by-step solutions.\n"
    "7. Output the summary directly — no preamble like 'I will...' or 'Here is...'.\n"
    "8. Skip garbled or unreadable text fragments.\n"
    "9. Write mathematical expressions using $...$ for inline math and $$...$$ (on its own line) for display equations. Example: the speed of sound is $c = \\sqrt{\\gamma P / \\rho}$.\n"
)

DEPTH_INSTRUCTIONS = {
    "Key points": (
        "Extract the most important concepts and ideas as a concise bullet list. "
        "Each bullet captures one distinct piece of knowledge. No prose, no padding."
    ),
    "Concise": (
        "Write a clear, fluent summary covering every main concept, definition, and conclusion. "
        "Use plain language suitable for exam revision. "
        "Let the content determine the length — do not pad or truncate artificially."
    ),
    "In-depth": (
        "Write a comprehensive, well-structured summary covering all concepts, definitions, "
        "methods, and how they relate to each other. "
        "Organise with headings or paragraphs as appropriate. "
        "Let the content determine the length — capture everything a student would need to know."
    ),
}

DEPTH_OPTIONS = list(DEPTH_INSTRUCTIONS.keys())


def auto_depth(word_count: int) -> str:
    if word_count < 400:
        return "Key points"
    elif word_count < 2000:
        return "Concise"
    else:
        return "In-depth"


def vision_prompt(existing_text: str = "") -> str:
    """Prompt sent to the vision model when describing a lecture slide image."""
    base = (
        "This is a slide from a lecture. "
        "Describe all visible content: text, equations, diagrams, charts, tables, and figures. "
        "For equations write them in plain text (e.g. 'E = mc^2', 'sum from i=1 to n of x_i'). "
        "For diagrams describe the structure (e.g. 'flowchart: A → B → C'). "
        "Be specific and complete — do not interpret, only describe what is visible. "
        "Write mathematical expressions using $...$ for inline and $$...$$ (on its own line) for display equations."
    )
    if existing_text.strip():
        base += (
            f"\n\nText already extracted from this slide (may be incomplete or garbled):\n"
            f"{existing_text.strip()}"
        )
    return base


def label_prompt(chunk: str) -> str:
    """Cheap skim: 5-word topic label only — no summary, no explanation."""
    return (
        "What is the main topic of this section? "
        "Reply in 5 words or fewer. No sentences — just the topic name.\n"
        "Use terms exactly as they appear in the text. Do not expand abbreviations.\n\n"
        "---\n\n"
        + chunk
        + "\n\n---\n\nTopic:"
    )


def adjacency_prompt(label_a: str, label_b: str) -> str:
    """Decide if two consecutive topic labels belong to the same group."""
    return (
        f"Topic A: {label_a}\n"
        f"Topic B: {label_b}\n\n"
        "Are these the same topic or a direct continuation? Answer only 'yes' or 'no'."
    )


def summary_prompt(text: str, depth: str, proficiency: str = "Intermediate") -> str:
    """Full summary of a block of text — used for both single-chunk and per-group summaries."""
    instruction = DEPTH_INSTRUCTIONS.get(depth, DEPTH_INSTRUCTIONS["Concise"])
    audience = PROFICIENCY_INSTRUCTIONS.get(proficiency, PROFICIENCY_INSTRUCTIONS["Intermediate"])
    return (
        f"{_PREAMBLE}\n{instruction}\n\n{audience}\n\n---\n\n{text}"
        "\n\n---\n\nSummary of the lecture theory:"
    )
