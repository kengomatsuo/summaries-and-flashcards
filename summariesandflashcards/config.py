OLLAMA_HOST = "http://localhost:11434"

# Default model pre-selected in the UI dropdown (the user can pick any installed
# model — a vision model enables image/equation reading, a text-only model is lighter).
DEFAULT_MODEL = "qwen2.5vl:3b"

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

# Vision speedups — a vision model tiles an image into patches, so a large image is
# much slower. Downscaling to VISION_MAX_PX before the call is ~4x faster at 512,
# ~1.6x at 768, with negligible quality loss for slide/page content.
VISION_MAX_PX = 768
VISION_NUM_PREDICT = 400   # token budget per image/page description
MIN_IMAGE_PX = 128         # images smaller than this (max dimension) are decorative → skip vision
BIG_IMAGE_PX = 300         # at/above this → always describe (figures, equation images)
TEXT_RICH_WORDS = 40       # slide text word count above which supplementary images are skipped

SUPPORTED_EXTENSIONS = [
    "pdf", "docx", "pptx", "xlsx", "xls",
    "txt", "md", "html", "htm", "csv", "json",
    "xml", "epub", "msg",
]

# Flashcards — content-proportional generation (one card per distinct fact).
# Per-topic ceiling guards a small model against padding a thin topic; the total
# cap bounds deck size / generation time.
FLASHCARD_MAX_PER_TOPIC = 5
FLASHCARD_MAX_TOTAL = 40
