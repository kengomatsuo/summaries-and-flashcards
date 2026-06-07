"""Text (and vision) extraction from uploaded files.

PDF and PPTX are handled with dedicated libraries that give per-page/slide
control and optional vision fallback.  Everything else goes through MarkItDown.
"""

from __future__ import annotations

import base64
import io
import os
import re
import tempfile
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import pymupdf
from markitdown import MarkItDown, StreamInfo
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from summariesandflashcards.config import VISION_RASTER_DPI
from summariesandflashcards.prompts import vision_prompt

if TYPE_CHECKING:
    from ollama import Client

_md = MarkItDown(enable_plugins=False)

# PDF font-encoding artifacts from MarkItDown when a PDF uses a custom glyph map.
_CID_RE = re.compile(r'\(cid:\d+\)')
_MEANINGFUL_RE = re.compile(r'[a-zA-Z]{5,}')

_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 2.0


def _clean(text: str) -> str:
    text = _CID_RE.sub('', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _retry(fn, retries: int = _RETRY_ATTEMPTS, delay: float = _RETRY_DELAY):
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ── Vision ────────────────────────────────────────────────────────────────────

def _vision_describe(client: "Client", model: str, img_b64: str, existing_text: str = "") -> str:
    """Call the vision model to describe one slide/page image."""
    prompt = vision_prompt(existing_text)

    def call():
        response = client.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [img_b64],
            }],
            options={"num_predict": 1000},
            stream=False,
        )
        return response["message"]["content"].strip()

    return _retry(call)


def _noise_ratio(text: str) -> float:
    """Fraction of whitespace-separated tokens that are ≤2 chars.

    High values (>0.35) indicate equation-heavy or garbled text where
    individual math symbols, operators, and isolated letters dominate.
    """
    tokens = text.split()
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if len(t) <= 2) / len(tokens)


# ── PDF via PyMuPDF ───────────────────────────────────────────────────────────

def _extract_pdf(
    file_bytes: bytes,
    vision_model: str = "",
    client: "Client | None" = None,
    on_page: "Callable[[int, int], None] | None" = None,
) -> str:
    """Extract text from a PDF, with optional vision fallback per page.

    Strategy per page:
    - Extract text with PyMuPDF.
    - If the page has embedded raster images OR the text is not meaningful
      (garbled encoding / image-only slide): rasterize the page and describe
      it with the vision model (covers equations drawn as vectors too, since
      the rendered image shows everything).
    - Pages with good text and no images use text only (fast path).

    Pages are joined with form-feed (\\x0c) so the existing segmentation
    pipeline handles them identically to form-feed-bearing PDFs.

    on_page(page_idx, total_pages) is called after each page completes.
    """
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    pages: list[str] = []
    total = len(doc)

    for page_idx, page in enumerate(doc):
        text = _clean(page.get_text())
        has_images = len(page.get_images()) > 0
        text_ok = bool(_MEANINGFUL_RE.search(text))
        # Equations typeset as PDF vector text pass _MEANINGFUL_RE (they
        # contain real words like "velocity") but produce a high ratio of
        # single-char tokens (operators, isolated symbols, numbers).
        equation_heavy = _noise_ratio(text) > 0.35

        use_vision = vision_model and client and (has_images or not text_ok or equation_heavy)

        if use_vision:
            pix = page.get_pixmap(dpi=VISION_RASTER_DPI)
            img_b64 = base64.b64encode(pix.tobytes("png")).decode()
            description = _vision_describe(client, vision_model, img_b64, text if text_ok else "")
            content = description
            if text_ok:
                # Keep extracted text too — vision covers images/equations on top
                content = text + "\n\n" + description
        elif text_ok:
            content = text
        else:
            # No vision model and no meaningful text — skip (garbage page)
            if on_page:
                on_page(page_idx, total)
            continue

        pages.append(content)
        if on_page:
            on_page(page_idx, total)

    doc.close()
    return "\x0c".join(pages)


# ── PPTX via python-pptx ──────────────────────────────────────────────────────

def _extract_pptx(
    file_bytes: bytes,
    vision_model: str = "",
    client: "Client | None" = None,
    on_page: "Callable[[int, int], None] | None" = None,
) -> str:
    """Extract text and images from a PPTX file.

    Per slide: extract all text shapes and table cells.  If the slide contains
    picture shapes and a vision model is available, describe each image and
    append the description inline.

    Slides are joined with form-feed (\\x0c).

    on_page(slide_idx, total_slides) is called after each slide completes.
    """
    prs = Presentation(io.BytesIO(file_bytes))
    slide_list = list(prs.slides)
    slides: list[str] = []
    total = len(slide_list)

    for slide_idx, slide in enumerate(slide_list):
        text_parts: list[str] = []
        image_descriptions: list[str] = []

        for shape in slide.shapes:
            # Text frames
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = para.text.strip()
                    if line:
                        text_parts.append(line)

            # Tables
            elif shape.has_table:
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        text_parts.append(" | ".join(cells))

            # Pictures
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and vision_model and client:
                img_b64 = base64.b64encode(shape.image.blob).decode()
                desc = _vision_describe(client, vision_model, img_b64)
                image_descriptions.append(f"[Image: {desc}]")

        slide_parts = [p for p in text_parts if p]
        if image_descriptions:
            slide_parts.extend(image_descriptions)

        content = "\n".join(slide_parts).strip()
        if content:
            slides.append(content)
        if on_page:
            on_page(slide_idx, total)

    return "\x0c".join(slides)


# ── Direct images ─────────────────────────────────────────────────────────────

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _extract_image(file_bytes: bytes, vision_model: str = "", client: "Client | None" = None) -> str:
    """Describe a standalone image file using the vision model."""
    if not (vision_model and client):
        return ""
    img_b64 = base64.b64encode(file_bytes).decode()
    return _vision_describe(client, vision_model, img_b64)


# ── MarkItDown fallback ───────────────────────────────────────────────────────

def _extract_markitdown(file_name: str, file_bytes: bytes) -> str:
    ext = os.path.splitext(file_name)[1].lower() or ".bin"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        result = _md.convert(tmp_path, stream_info=StreamInfo(extension=ext, filename=file_name))
        return _clean(result.text_content or "")
    finally:
        os.unlink(tmp_path)


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(
    file_name: str,
    file_bytes: bytes,
    vision_model: str = "",
    client: "Client | None" = None,
    on_page: "Callable[[int, int], None] | None" = None,
) -> str:
    """Extract text (and optional vision descriptions) from an uploaded file.

    Args:
        file_name:    Original filename — used to determine format.
        file_bytes:   Raw file content.
        vision_model: Ollama model name to use for image description.
                      Empty string disables vision.
        client:       Ollama Client instance.  Required when vision_model is set.
        on_page:      Optional callback(page_idx, total_pages) called after each
                      page/slide completes. Used for progress reporting.
    """
    ext = os.path.splitext(file_name)[1].lower()

    if ext == ".pdf":
        return _extract_pdf(file_bytes, vision_model, client, on_page)
    if ext in (".pptx", ".ppt"):
        return _extract_pptx(file_bytes, vision_model, client, on_page)
    if ext in _IMAGE_EXTENSIONS:
        return _extract_image(file_bytes, vision_model, client)

    # Everything else: DOCX, XLSX, HTML, TXT, MD, CSV, etc.
    return _extract_markitdown(file_name, file_bytes)
