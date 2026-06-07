import ollama
from ollama import Client
from summariesandflashcards.config import OLLAMA_HOST, DEFAULT_MODEL, VISION_MODEL_PATTERNS


def is_up() -> bool:
    try:
        Client(host=OLLAMA_HOST).list()
        return True
    except Exception:
        return False


def list_models() -> list[str]:
    """Return names of all locally installed Ollama models."""
    try:
        response = Client(host=OLLAMA_HOST).list()
        return [m.model for m in response.models if m.model]
    except Exception:
        return []


def has_model(name: str) -> bool:
    return name in list_models()


def is_vision_model(name: str) -> bool:
    """True if the model name matches a known vision-capable model pattern."""
    name_lower = name.lower()
    return any(p in name_lower for p in VISION_MODEL_PATTERNS)
