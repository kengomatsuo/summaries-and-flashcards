# Third-Party Attributions — Summaries and Flashcards

Summaries and Flashcards is built on open-source software. This file credits every library in the
dependency tree. The "Scope" column marks whether a package is a **direct** dependency
(listed in `requirements.txt`) or a **transitive** one (pulled in automatically).

Generated: 2026-06-06 · Python 3.12.10 · .venv verified

---

## ⚠ Licence notes

All packages are permissively licensed (MIT, BSD, Apache-2.0, MPL-2.0 or compatible).
One package in the transitive tree carries an LGPL notice:

| Package | License | Notes |
|---|---|---|
| `frozendict` | LGPL v3 | Transitive dep of `genanki`. LGPL requires that *the library itself* remain modifiable by end-users; it does **not** require our project to become LGPL. Because it is installed as a standard pip package (dynamically linked), this is compliant with no extra action required. |
| `certifi` | MPL-2.0 | Transitive dep of `requests`. Mozilla Public License 2.0 is file-level copyleft; unmodified distribution (pip install) is compliant. |

---

## Runtime requirement — Ollama (not a pip package)

| Component | Version | License | Author | Source |
|---|---|---|---|---|
| Ollama | latest | MIT | Ollama, Inc. | https://github.com/ollama/ollama |

Ollama is a separately installed native binary required to run the local LLM. It is not
distributed with Summaries and Flashcards. Users install it independently from https://ollama.com.

---

## Direct dependencies (`requirements.txt`)

| Package | Version | License | Author / Maintainer | Homepage |
|---|---|---|---|---|
| streamlit | 1.58.0 | Apache-2.0 | Snowflake Inc \<hello@streamlit.io\> | https://streamlit.io |
| markitdown | 0.1.6 | MIT | Adam Fourney, Microsoft | https://github.com/microsoft/markitdown |
| ollama (Python client) | 0.6.2 | MIT | hello@ollama.com | https://ollama.com |
| genanki | 0.13.1 | MIT | Kerrick Staley | https://github.com/kerrickstaley/genanki |

---

## Full transitive dependency tree

| Package | Version | License | Author |
|---|---|---|---|
| altair | 6.2.1 | BSD-3-Clause | Vega-Altair Contributors |
| annotated-types | 0.7.0 | MIT | Adrian Garcia Badaracco, Samuel Colvin, Zac Hatfield-Dodds |
| anyio | 4.13.0 | MIT | Alex Grönholm |
| attrs | 26.1.0 | MIT | Hynek Schlawack |
| beautifulsoup4 | 4.14.3 | MIT | Leonard Richardson |
| blinker | 1.9.0 | MIT | Jason Kirtland |
| cached-property | 2.0.1 | BSD | Daniel Roy Greenfeld |
| cachetools | 7.1.4 | MIT | Thomas Kemmer |
| certifi | 2026.5.20 | MPL-2.0 | Kenneth Reitz |
| cffi | 2.0.0 | MIT | Armin Rigo, Maciej Fijalkowski |
| charset-normalizer | 3.4.7 | MIT | Ahmed R. TAHRI |
| chevron | 0.14.0 | MIT | Noah Morrison |
| click | 8.4.1 | BSD-3-Clause | Pallets (Armin Ronacher et al.) |
| cobble | 0.1.4 | MIT | Michael Williamson |
| cryptography | 48.0.0 | Apache-2.0 OR BSD-3-Clause | Python Cryptographic Authority |
| defusedxml | 0.7.1 | PSFL | Christian Heimes |
| et-xmlfile | 2.0.0 | MIT | openpyxl team |
| flatbuffers | 25.12.19 | Apache-2.0 | Google (Derek Bailey) |
| frozendict | 2.4.7 | LGPL v3 | Marco Sulla |
| gitdb | 4.0.12 | BSD-3-Clause | Sebastian Thiel |
| GitPython | 3.1.50 | BSD-3-Clause | Sebastian Thiel, Michael Trier |
| h11 | 0.16.0 | MIT | Nathaniel J. Smith |
| httpcore | 1.0.9 | BSD-3-Clause | Tom Christie |
| httptools | 0.8.0 | MIT | Yury Selivanov |
| httpx | 0.28.1 | BSD-3-Clause | Tom Christie |
| idna | 3.18 | BSD-3-Clause | Kim Davies |
| itsdangerous | 2.2.0 | BSD-3-Clause | Pallets |
| Jinja2 | 3.1.6 | BSD-3-Clause | Pallets |
| jsonschema | 4.26.0 | MIT | Julian Berman |
| jsonschema-specifications | 2025.9.1 | MIT | Julian Berman |
| lxml | 6.1.1 | BSD-3-Clause | lxml dev team |
| magika | 0.6.3 | Apache-2.0 | Magika Developers, Google |
| mammoth | 1.11.0 | BSD-2-Clause | Michael Williamson |
| markdownify | 1.2.2 | MIT | Matthew Tretter |
| MarkupSafe | 3.0.3 | BSD-3-Clause | Pallets |
| narwhals | 2.22.1 | MIT | Marco Gorelli |
| numpy | 2.4.6 | BSD-3-Clause (+ MIT, 0BSD, Zlib, CC0-1.0) | NumPy Developers (Travis Oliphant et al.) |
| olefile | 0.47 | BSD | Philippe Lagadec |
| onnxruntime | 1.26.0 | MIT | Microsoft Corporation |
| openpyxl | 3.1.5 | MIT | openpyxl Authors |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause | Donald Stufft |
| pandas | 3.0.3 | BSD-3-Clause | Pandas Development Team |
| pdfminer.six | 20251230 | MIT | Yusuke Shinyama, Pieter Marsman |
| pdfplumber | 0.11.9 | MIT | Jeremy Singer-Vine |
| pillow | 12.2.0 | MIT-CMU | Jeffrey A. Clark (Alex) |
| protobuf | 7.35.0 | BSD-3-Clause | Google |
| pyarrow | 24.0.0 | Apache-2.0 | Apache Arrow authors |
| pycparser | 3.0 | BSD-3-Clause | Eli Bendersky |
| pydantic | 2.13.4 | MIT | Samuel Colvin et al. |
| pydantic-core | 2.46.4 | MIT | Samuel Colvin et al. |
| pydeck | 0.9.2 | Apache-2.0 | Andrew Duberstein (vis.gl) |
| pypdfium2 | 5.9.0 | BSD-3-Clause / Apache-2.0 | pypdfium2-team |
| python-dateutil | 2.9.0.post0 | Apache-2.0 AND BSD | Gustavo Niemeyer, Paul Ganssle |
| python-dotenv | 1.2.2 | BSD-3-Clause | Saurabh Kumar |
| python-multipart | 0.0.32 | Apache-2.0 | Andrew Dunham |
| python-pptx | 1.0.2 | MIT | Steve Canny |
| PyYAML | 6.0.3 | MIT | Kirill Simonov |
| referencing | 0.37.0 | MIT | Julian Berman |
| regex | 2026.5.9 | Apache-2.0 AND CNRI-Python | Matthew Barnett |
| requests | 2.34.2 | Apache-2.0 | Kenneth Reitz |
| rpds-py | 2026.5.1 | MIT | Julian Berman |
| six | 1.17.0 | MIT | Benjamin Peterson |
| smmap | 5.0.3 | BSD-3-Clause | Sebastian Thiel |
| soupsieve | 2.8.4 | MIT | Isaac Muse |
| starlette | 1.2.1 | BSD-3-Clause | Tom Christie |
| tenacity | 9.1.4 | Apache-2.0 | Julien Danjou |
| toml | 0.10.2 | MIT | William Pearson |
| typing-extensions | 4.15.0 | PSF-2.0 | Guido van Rossum et al. |
| typing-inspection | 0.4.2 | MIT | Victorien Plot |
| urllib3 | 2.7.0 | MIT | Andrey Petrov |
| uvicorn | 0.49.0 | BSD-3-Clause | Tom Christie |
| websockets | 16.0 | BSD-3-Clause | Aymeric Augustin |
| xlrd | 2.0.2 | BSD | Chris Withers |
| XlsxWriter | 3.2.9 | BSD-2-Clause | John McNamara |
