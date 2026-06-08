#!/usr/bin/env python3
"""Pre-flight check: verifies Ollama is running and the default model is pulled."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from summariesandflashcards import ollama_client
from summariesandflashcards.config import DEFAULT_MODEL

OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"


def check(label: str, passed: bool, fix: str = "") -> bool:
    mark = OK if passed else FAIL
    print(f"  {mark}  {label}")
    if not passed and fix:
        print(f"      → {fix}")
    return passed


def main() -> None:
    print("\nSummaries and Flashcards — setup check\n")

    all_ok = True

    up = ollama_client.is_up()
    all_ok &= check(
        "Ollama server is running",
        up,
        "Run: ollama serve",
    )

    if up:
        models = ollama_client.list_models()
        all_ok &= check(
            "At least one Ollama model is installed",
            bool(models),
            f"Run: ollama pull {DEFAULT_MODEL}",
        )
        if models:
            print(f"\n  Installed models: {', '.join(models)}")
    else:
        all_ok = False

    print()
    if all_ok:
        print("All checks passed. Run the app with:")
        print("  streamlit run app.py\n")
    else:
        print("Fix the issues above, then re-run this script.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
