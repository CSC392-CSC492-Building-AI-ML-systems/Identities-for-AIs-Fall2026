import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "agent"))
import identify_api

# OLD ver. commented out because identify_api already
# imports cardlib through card_lookup:
# sys.path.insert(0, str(ROOT / "cards"))
# from cardlib import build_card

# update: added get_questions, run_check, collected_answers


def get_questions():
    """NEW: the 6 probe questions the system needs answered: {probe id: question}."""
    return identify_api.get_probes()


def run_check(answers, domain, deployment=None, test_mode=True):
    """NEW: send the chatbot's answers to the real system and return its result.
    test_mode=True uses a fake judge (no API calls, no cost)."""
    return identify_api.identify(
        answers,
        domain=domain,
        deployment=deployment or None,
        judge_provider="mock" if test_mode else "google",
    )


# OLD: fake identifier. Commented out because the real system replaces it.
# def identify(answer_text):
#     """FAKE for now. Later we swap this for Tiana's real identifier."""
#     return {
#         "family": "Llama",
#         "version": "Llama 3.1 8B",
#         "family_confidence": 0.9,
#         "version_confidence": 0.7,
#         "reason": "Mock result, replace with the real identifier.",
#     }

# The identifier says "Llama 3.1 8B" but cards use keys like "llama3.1-8b"
VERSION_TO_KEY = {
    "Llama 3.1 8B": "llama3.1-8b",
    "Qwen3 8B": "qwen3-8b",
    "Gemma 3 4B": "gemma3-4b",
}

# OLD: get_card(). Commented out because identify_api.identify() now attaches
# the card itself (version -> family -> developer) using card_lookup.py.
# def get_card(result):
#     key = VERSION_TO_KEY.get(result["version"])
#     if key:
#         return build_card(key)                    # exact model known
#     return build_card(family=result["family"])    # only family known

RAW = ROOT / "collector" / "data" / "raw"


def sample_answer(model_key):
    """Pick a real collected answer from a model's data file."""
    rows = []
    for f in sorted((RAW / model_key).glob("*.jsonl")):
        with open(f) as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    if r.get("response_text") and not r.get("error"):
                        rows.append(r)
    return random.choice(rows)["response_text"] if rows else ""


def collected_answers(model_key, persona=None):
    """NEW: act as a stand-in company chatbot. Returns {probe id: answer} for the 6
    probe questions, taken from the collected data of one model."""
    wanted = set(get_questions())
    found = {}
    for f in sorted((RAW / model_key).glob("*.jsonl")):
        with open(f) as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                pid = r.get("prompt_id")          # field name guessed, see note below
                text = r.get("response_text")
                if pid in wanted and pid not in found and text and not r.get("error"):
                    if persona and r.get("persona_id") != persona:
                        continue
                    found[pid] = text
    return found