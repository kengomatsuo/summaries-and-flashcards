# Global Preferences

## Git
Before checking out a different branch, always `git stash` first. After finishing work on the other branch, return to the original branch and run `git stash pop`.

## CLAUDE.md
Keep `CLAUDE.md` up to date. Whenever a change affects how the project is built, deployed, structured, or understood, update the project's `CLAUDE.md` to reflect it — without being asked. If no `CLAUDE.md` exists and the project is non-trivial, run `/init` to create one.

## Research rule — NEVER skip this

The goal of this entire ruleset is simple: **never rely on the knowledge base. Ever.** Training data is guaranteed to be stale, wrong, or deprecated — libraries change, APIs are removed, bugs get filed, and the knowledge base always lags behind. All facts about libraries, APIs, errors, and platform behaviour must come from live sources fetched in the current session.

**Before writing any code that uses a library API** — fetch the official docs. No guessing. No assuming. Docs first, code after.

**Before answering any question about a library, API, or error** — web-search the issue first, then fetch the relevant page. Even simple factual questions ("does X support Y?", "why does Z fail?") must be answered from fetched content, not memory. A wrong confident answer is worse than saying "let me check."

**Before diagnosing any build error, bundler error, or runtime crash** — search the web for the exact error message + relevant package names. Check GitHub issues and official docs before proposing a fix.

## Always propose before implementing — NEVER skip this

**Never start writing or editing code without first telling the user what you plan to do and getting confirmation.**
State the approach, the files that will change, and any tradeoffs. Wait for the user to say yes before touching any code.
This applies to every non-trivial change. The only exception is a fix so small and obvious that it fits in one sentence and has no alternatives.
