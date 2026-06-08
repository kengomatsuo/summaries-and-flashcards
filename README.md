# Summaries and Flashcards

AI-powered lecture notes summariser — fully local, no internet required, no paid API.

Upload your notes (PDF, DOCX, PPTX, and more), get a faithful summary and
exportable Anki flashcards — all running on your own machine.

---

## What you need

| Requirement | Minimum | Notes |
|---|---|---|
| OS | Windows 10, macOS 14 Sonoma, Linux | |
| RAM | 8 GB | 16 GB recommended for 7–8B models or large docs |
| Storage | ~5 GB free | For the Ollama model |
| Python | 3.12 | 3.10 is the hard floor; do not use 3.14+ |
| GPU | Not required | Speeds up inference if available |

---

## 1 — Install Ollama

Ollama runs the local AI model. Install it **once**, outside of Python.

### macOS

```sh
# Option A — Homebrew (recommended: runs as a background service)
brew install ollama
brew services start ollama

# Option B — native app (menu bar icon, auto-starts on login)
# Download Ollama.dmg from https://ollama.com/download/mac
```

### Windows

Open **PowerShell** and run:

```powershell
irm https://ollama.com/install.ps1 | iex
```

Or download the installer directly from [ollama.com/download/windows](https://ollama.com/download/windows).

After installation, Ollama runs as a background service automatically.

### Linux

```sh
curl -fsSL https://ollama.com/install.sh | sh
```

---

## 2 — Pull the two required models

```sh
ollama pull qwen2.5vl:3b   # 3.2 GB — vision: reads equations, diagrams, images in slides
ollama pull qwen2.5:3b     # 1.9 GB — text: writes the summaries
```

You only need to do this once. The app uses a fixed pair: the vision model extracts
content from slides/pages, then is unloaded and the text-only model writes the summary.
The text-only model is a stronger instruction-follower than its vision sibling, and
unloading the vision model first keeps peak RAM at ~3.2 GB (not the sum). There is no
model picker in the app — these two names are set in `summariesandflashcards/config.py`
(`DEFAULT_MODEL` and `TEXT_MODEL`).

---

## 3 — Install Python 3.12

Skip this step if you already have Python 3.12 installed (`python --version`).

### macOS (pyenv)

```sh
# Install pyenv if you don't have it
brew install pyenv

# Install Python 3.12 and pin it to this project
pyenv install 3.12.10
pyenv local 3.12.10        # creates .python-version in the project folder
```

### Windows

Download the **Python 3.12** installer from
[python.org/downloads](https://www.python.org/downloads/) and run it.

> During setup, tick **"Add Python to PATH"** before clicking Install.

Verify in a new terminal:

```powershell
python --version   # should print Python 3.12.x
```

### Linux

```sh
# Ubuntu / Debian
sudo apt update && sudo apt install python3.12 python3.12-venv

# Or via pyenv (all distros)
curl https://pyenv.run | bash
pyenv install 3.12.10
pyenv local 3.12.10
```

---

## 4 — Create the virtual environment

Run these commands from inside the project folder.

### macOS / Linux

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If you see an `UnauthorizedAccess` error on Windows, run:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## 5 — Verify the setup

```sh
python scripts/setup_check.py
```

Expected output:

```
Summaries and Flashcards — setup check

  ✓  Ollama server is running
  ✓  Required model 'qwen2.5vl:3b' is installed
  ✓  Required model 'qwen2.5:3b' is installed

  Installed models: qwen2.5:3b, qwen2.5vl:3b

All checks passed. Run the app with:
  streamlit run app.py
```

---

## 6 — Run the app

```sh
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Supported file formats

| Format | Extension(s) |
|---|---|
| PDF | `.pdf` |
| Word | `.docx` |
| PowerPoint | `.pptx` |
| Excel | `.xlsx`, `.xls` |
| Plain text | `.txt`, `.md`, `.csv`, `.json`, `.xml` |
| Web | `.html`, `.htm` |
| E-book | `.epub` |
| Outlook | `.msg` |

---

## System requirements (detailed)

| Library | Version | Python floor | Python ceiling |
|---|---|---|---|
| Streamlit | 1.58.0 | 3.10 | 3.14 |
| MarkItDown | 0.1.6 | 3.10 | 3.13 |
| ollama (client) | 0.6.2 | 3.8 | — |
| PyMuPDF | 1.27.2 | 3.10 | — |
| python-pptx | 1.0.2 | 3.8 | — |
| Pillow | 12.2.0 | 3.10 | — |
| Markdown | 3.10.2 | 3.10 | — |
| latex2mathml | 3.81.0 | 3.10 | — |
| genanki | 0.13.1 | 3.6 | — |

The combined floor is **Python 3.10**; the combined ceiling is **Python 3.13**.
Python 3.12 is the recommended version.

---

## Troubleshooting

**`zsh: command not found: ollama` / `ollama is not recognized`**
Ollama is not installed or not on your PATH. Repeat step 1.

**`Required model(s) not installed` warning in the app**
Run `ollama pull qwen2.5vl:3b` and `ollama pull qwen2.5:3b`, then refresh the page.

**Scanned / image-only PDFs produce no text**
Use a vision-capable model (e.g. `qwen2.5vl:3b`). The app automatically rasterises
pages that have no readable text and sends them to the vision model for description.

**Slow summarisation**
This is normal on CPU-only machines. The 3B model is the fastest option.
Streaming output means you see results progressively rather than waiting for the
full response.

---

## Attributions

See [ATTRIBUTIONS.md](ATTRIBUTIONS.md) for a full list of open-source libraries
used and their licences.
