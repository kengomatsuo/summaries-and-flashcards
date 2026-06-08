"""Single-pass summarisation (lite): one LLM call over the whole document."""

import time
from collections.abc import Iterator
from typing import Callable

from ollama import Client

from summariesandflashcards.config import OLLAMA_HOST
from summariesandflashcards.prompts import summary_prompt

_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 2.0


def _with_retry(fn: Callable, retries: int = _RETRY_ATTEMPTS, delay: float = _RETRY_DELAY):
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def summarize_stream(
    text: str,
    model: str,
    depth: str,
    proficiency: str = "Intermediate",
) -> Iterator[str]:
    """Stream a single-pass summary of `text` (the whole document in one call)."""
    prompt = summary_prompt(text, depth, proficiency)
    client = Client(host=OLLAMA_HOST)
    stream = _with_retry(lambda: client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0},
        stream=True,
    ))
    for chunk in stream:
        token = chunk["message"]["content"]
        if token:
            yield token
