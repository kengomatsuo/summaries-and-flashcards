OLLAMA_HOST = "http://localhost:11434"

DEFAULT_MODEL = "qwen2.5vl:3b"

# Text model for the skim/group/write phases. A vision (VL) model is a weaker
# instruction-follower than its text-only sibling of the same size, so when the
# selected model is vision-capable we route the *text* phases here instead.
# Falls back to the selected model if this is not installed. Pull with:
#   ollama pull qwen2.5:3b
TEXT_MODEL = "qwen2.5:3b"

# Vision model detection — any installed model whose name contains one of
# these substrings is treated as vision-capable.
VISION_MODEL_PATTERNS = [
    "llava", "moondream", "minicpm-v", "minicpm_v",
    "qwen2.5vl", "qwen3-vl", "deepseek-ocr", "glm-ocr",
    "bakllava",
]

# Suggested vision models (lightweight, ~3B class).
SUGGESTED_VISION_MODELS = [
    "qwen2.5vl:3b",    # 3.2 GB — recommended, strong document/slide understanding
    "moondream:1.8b",  # 1.7 GB — smallest option
    "deepseek-ocr:3b", # 3 B   — OCR-specialised
    "llava:7b",        # 4.7 GB — general vision
]

# DPI used when rasterising a PDF page for the vision model.
VISION_RASTER_DPI = 150

SUPPORTED_EXTENSIONS = [
    "pdf", "docx", "pptx", "xlsx", "xls",
    "txt", "md", "html", "htm", "csv", "json",
    "xml", "epub", "msg",
]

# Approximate reading speed used for "minutes saved" calculation
READING_WPM = 200

# Chunking — max chars per chunk sent to the LLM, and overlap between chunks
CHUNK_MAX_CHARS = 6000
CHUNK_OVERLAP_CHARS = 400

# Recursive reduce — max summaries per intermediate reduce batch
GROUP_SIZE = 15

# Hallucination gate: a topic group whose *teachable* word count (excluding file
# headers, image captions, and "STEP n OF m" labels) is below this is NOT sent to
# the writer — bare title/label/image slides make small models invent content.
# Tune up to drop more aggressively, down to keep terser slides. Title slides in
# this corpus run ~8–9 words; pipeline-step labels ("Result") run 1–3.
MIN_GROUP_WORDS = 12
