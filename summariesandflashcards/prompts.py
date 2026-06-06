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

# Used in map step (no surrounding context available yet — exercises are ID'd but not discussed)
_MAP_PREAMBLE = (
    "You are summarising one section of lecture notes.\n\n"
    "RULES:\n"
    "1. ONLY include information explicitly in this section. Do NOT add background knowledge.\n"
    "2. Write about the theory: concepts, definitions, algorithms, methods.\n"
    "3. If this section is an exercise or practice problem, identify in one sentence what concept it is practising. Do NOT solve it.\n"
    "4. NEVER write step-by-step solutions or 'Final answer'.\n"
    "5. Output the summary directly — no preamble like 'I will...' or 'Here is...'.\n"
    "6. Skip garbled or unreadable text fragments.\n"
)

# Used in group reduce and final reduce (surrounding context is present — exercises can reference theory)
_REDUCE_PREAMBLE = (
    "You are a lecture summariser. Your ONLY job is to summarise the theory and concepts taught.\n\n"
    "STRICT RULES:\n"
    "1. ONLY include information explicitly present in the provided notes. Do NOT add background knowledge or concepts not in the text.\n"
    "2. Cover ALL topics — do not skip any section.\n"
    "3. If files are labelled 'File 1 of N', 'File 2 of N', etc., they are in course order — earlier files introduce concepts later files build on.\n"
    "4. Write about the theory: concepts, definitions, algorithms, methods.\n"
    "5. When a section contains exercises or practice problems, discuss what they are practising and reference the relevant theory or formula that precedes them. Do NOT solve them or show step-by-step calculations.\n"
    "6. NEVER write 'Final answer', worked calculations, or step-by-step solutions.\n"
    "7. Output the summary directly — no preamble like 'I will...' or 'Here is...'.\n"
    "8. Skip garbled or unreadable text fragments.\n"
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


def summary_prompt(text: str, depth: str, proficiency: str = "Intermediate") -> str:
    instruction = DEPTH_INSTRUCTIONS.get(depth, DEPTH_INSTRUCTIONS["Concise"])
    audience = PROFICIENCY_INSTRUCTIONS.get(proficiency, PROFICIENCY_INSTRUCTIONS["Intermediate"])
    return (
        f"{_REDUCE_PREAMBLE}\n{instruction}\n\n{audience}\n\n---\n\n{text}"
        "\n\n---\n\nSummary of the lecture theory:"
    )


def map_prompt(chunk: str, proficiency: str = "Intermediate") -> str:
    audience = PROFICIENCY_INSTRUCTIONS.get(proficiency, PROFICIENCY_INSTRUCTIONS["Intermediate"])
    return (
        f"{_MAP_PREAMBLE}\n{audience}\n\n---\n\n{chunk}"
        "\n\n---\n\nSection summary:"
    )


def adjacency_prompt(title_a: str, summary_a: str, title_b: str, summary_b: str) -> str:
    return (
        f"Section A — {title_a}:\n{summary_a}\n\n"
        f"Section B — {title_b}:\n{summary_b}\n\n"
        "Is section B a direct continuation of, or an exercise/application of, section A? "
        "Answer only 'yes' or 'no'."
    )


def group_reduce_prompt(
    items: list[tuple[str, str]],
    proficiency: str = "Intermediate",
) -> str:
    """Reduce a topic group — theory and its exercises together.

    items: list of (title, summary) for each chunk in the group.
    """
    audience = PROFICIENCY_INSTRUCTIONS.get(proficiency, PROFICIENCY_INSTRUCTIONS["Intermediate"])
    parts = "\n\n".join(
        f"[{i}] {title}\n{summary}" for i, (title, summary) in enumerate(items)
    )
    return (
        "The following sections belong to the same topic.\n"
        "Merge them into one faithful summary of the theory and key concepts.\n"
        "Where an exercise or practice problem appears, explain what concept or formula "
        "from the theory in this group it is practising — do NOT solve it or show calculations.\n\n"
        f"{audience}\n\n---\n\n{parts}"
        "\n\n---\n\nGroup summary:"
    )


def link_prompt(summaries: list[str]) -> str:
    numbered = "\n\n".join(f"[{i}] {s}" for i, s in enumerate(summaries))
    return (
        "Below are numbered topic summaries from a course, in order.\n"
        "Analyse the connections: which topics introduce concepts used in later topics, "
        "which build on each other, and which are standalone.\n"
        "Write a concise plain-text connection analysis. Do not rewrite the summaries.\n\n"
        + numbered
    )


def reduce_prompt(
    combined: str,
    depth: str,
    proficiency: str = "Intermediate",
    connection_analysis: str = "",
) -> str:
    instruction = DEPTH_INSTRUCTIONS.get(depth, DEPTH_INSTRUCTIONS["Concise"])
    audience = PROFICIENCY_INSTRUCTIONS.get(proficiency, PROFICIENCY_INSTRUCTIONS["Intermediate"])
    context = (
        f"Connection analysis — use this to understand how topics relate:\n"
        f"{connection_analysis}\n\n"
        if connection_analysis else ""
    )
    return (
        f"{_REDUCE_PREAMBLE}\n{instruction}\n\n{audience}\n\n{context}"
        "The numbered summaries below cover the topics of a longer document in order. "
        "Synthesise them into one coherent final summary.\n\n"
        "---\n\n"
        + combined
        + "\n\n---\n\nSummary of the lecture theory:"
    )
