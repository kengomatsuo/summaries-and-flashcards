import os
import re
import tempfile
from markitdown import MarkItDown, StreamInfo

_md = MarkItDown(enable_plugins=False)

# PDF font-encoding artifacts produced by MarkItDown when a PDF uses a custom
# glyph map that cannot be decoded back to Unicode.
_CID_RE = re.compile(r'\(cid:\d+\)')


def _clean(text: str) -> str:
    text = _CID_RE.sub('', text)
    # Collapse runs of whitespace left behind by removed tokens
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_text(file_name: str, file_bytes: bytes) -> str:
    """Convert uploaded file bytes to plain text via MarkItDown.

    Writes to a temp file so MarkItDown can detect the format from the
    extension — more reliable than passing a raw stream without a name.
    """
    ext = os.path.splitext(file_name)[1].lower() or ".bin"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        result = _md.convert(tmp_path, stream_info=StreamInfo(extension=ext, filename=file_name))
        return _clean(result.text_content or "")
    finally:
        os.unlink(tmp_path)
