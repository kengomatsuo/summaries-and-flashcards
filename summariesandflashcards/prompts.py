PROFICIENCY_OPTIONS = ["Beginner", "Intermediate", "Expert"]

PROFICIENCY_INSTRUCTIONS = {
    "Beginner": (
        "Write for a reader who is new to this subject. "
        "The first time a technical term from the notes appears, define it briefly using only what the notes support. "
        "Prefer plain language. "
        "Do not invent analogies or examples that are not grounded in the notes."
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
    "You summarise lecture notes. You may use ONLY facts that appear in the NOTES below.\n\n"
    "MOST IMPORTANT RULE: if a fact is not written in the notes, do not write it. "
    "Do not add definitions, background, examples, formulas, history, or related topics from "
    "your own knowledge — even if they are true and relevant. A short summary that stays "
    "faithful to the notes is correct; a longer one that adds outside facts is wrong.\n\n"
    "Summarise the specifics written in the notes below. The notes are often terse — a list of "
    "datasets, tools, parameters, targets, or short bullets. Restate them clearly and "
    "completely, in your own words; do not drop a point for being brief, and do not copy the "
    "notes verbatim. Empty slides (bare titles, step labels, image-only slides) are removed "
    "before you see them, so assume the notes below have real content worth conveying — your "
    "job is to convey it, not to judge whether it qualifies.\n\n"
    "HOW TO WRITE:\n"
    "- Start directly with the first real concept. Do NOT begin with 'The lecture covered', "
    "'This slide', 'This section', 'In this section', 'Here', or 'I will'.\n"
    "- A line beginning with '[Image:' is a caption describing a picture on the slide, not "
    "lecture theory. Refer to it only if the slide's own text discusses it; never expand a "
    "caption into its own topic.\n"
    "- For an exercise or practice problem: state the question exactly as written, then name "
    "which concept or formula from the notes applies and why. NEVER solve it, show worked "
    "calculations, or write 'Final answer'.\n"
    "- Skip garbled or unreadable fragments.\n"
    "- Write mathematics using $...$ for inline and $$...$$ (on its own line) for display "
    "equations. Example: the speed of sound is $c = \\sqrt{\\gamma P / \\rho}$.\n"
    "- Match length to the notes: one line of source becomes at most one sentence. Never pad.\n\n"
    "Before each sentence, check: is this fact in the notes above? If not, leave it out."
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
        "Explain each concept, definition, and method THAT APPEARS IN THE NOTES in full, and "
        "how they relate to each other. Organise with headings or paragraphs as appropriate. "
        "Depth must come from explaining what is present in the notes — never from adding "
        "material the notes do not contain. The notes determine the length."
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


def skim_prompt(chunk: str) -> str:
    """Skim a section: produce a short topic label and a 1-2 sentence context description."""
    return (
        "Analyse this lecture section. Use only words and facts that appear in it.\n\n"
        "---\n\n"
        + chunk
        + "\n\n---\n\n"
        "Reply in this exact format (two lines only):\n"
        "TOPIC: <topic in 5 words or fewer, using terms exactly as they appear. If the section "
        "has no teachable content — only a title, heading, step label, metadata, or image "
        "caption — write exactly: (none)>\n"
        "CONTEXT: <1 sentence describing the concepts, equations, or methods actually present. "
        "If there is no teachable content, write exactly: none>"
    )


def adjacency_prompt(context_a: str, context_b: str) -> str:
    """Decide if two consecutive sections belong to the same topic group."""
    return (
        f"Section A covers: {context_a}\n"
        f"Section B covers: {context_b}\n\n"
        "Answer 'yes' if: these sections cover the same topic, Section B is a direct continuation or next step of Section A, or Section A appears to be a title or heading that introduces Section B. Otherwise answer 'no'. Answer only 'yes' or 'no'."
    )


def summary_prompt(text: str, depth: str, proficiency: str = "Intermediate") -> str:
    """Full summary of a block of text — used for both single-chunk and per-group summaries."""
    instruction = DEPTH_INSTRUCTIONS.get(depth, DEPTH_INSTRUCTIONS["Concise"])
    audience = PROFICIENCY_INSTRUCTIONS.get(proficiency, PROFICIENCY_INSTRUCTIONS["Intermediate"])
    return (
        f"{_PREAMBLE}\n{instruction}\n\n{audience}\n\n---\n\n{text}"
        "\n\n---\n\nSummary of the lecture theory:"
    )


def flashcard_prompt(text: str, n: int) -> str:
    """Ask the model for up to `n` Q&A flashcards grounded strictly in `text`.

    Output contract: a bare JSON array of {"q","a"} objects, no prose, no fences.
    """
    return (
        "You create Anki flashcards from a study summary.\n\n"
        f"Create up to {n} question/answer pairs that test the key facts in the SUMMARY below.\n"
        "STRICT RULES:\n"
        "1. Use ONLY facts stated in the summary. Do not add outside knowledge, definitions, or examples not present.\n"
        f"2. If the summary is too thin for {n} good cards, make fewer. Quality over quantity.\n"
        "3. Each question must be specific and answerable from the summary alone. Each answer is concise — a phrase or a single sentence.\n"
        "4. Do not write questions about the document structure (e.g. 'what is step 3') — ask about the concept itself.\n"
        "5. Output ONLY a JSON array and nothing else — no prose, no markdown code fences. "
        'Format: [{"q": "...", "a": "..."}, ...]\n\n'
        "SUMMARY:\n---\n"
        f"{text}\n"
        "---\n\n"
        "JSON array:"
    )
