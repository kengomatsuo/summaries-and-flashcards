OLLAMA_HOST = "http://localhost:11434"

DEFAULT_MODEL = "llama3.2:3b"

SUGGESTED_MODELS = [
    "llama3.2:3b",
    "qwen2.5:3b",
    "phi4-mini",
    "gemma2:2b",
    "qwen2.5:7b",
    "llama3.1:8b",
]

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
