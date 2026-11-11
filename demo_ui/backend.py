import sys
sys.path.insert(0, "cards")   # lets us use the team's model card code
from cardlib import build_card

def identify(answer_text):
    """FAKE for now. Later we swap this for Tiana's real identifier."""
    return {
        "family": "Llama",
        "version": "Llama 3.1 8B",
        "family_confidence": 0.9,
        "version_confidence": 0.7,
        "reason": "Mock result, replace with the real identifier.",
    }

# The identifier says "Llama 3.1 8B" but cards use keys like "llama3.1-8b"
VERSION_TO_KEY = {
    "Llama 3.1 8B": "llama3.1-8b",
    "Qwen3 8B": "qwen3-8b",
    "Gemma 3 4B": "gemma3-4b",
}

def get_card(result):
    key = VERSION_TO_KEY.get(result["version"])
    if key:
        return build_card(key)                    # exact model known
    return build_card(family=result["family"])    # only family known