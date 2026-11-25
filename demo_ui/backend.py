import json
import random
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Setup: find the repo root and make Tiana's `agent/` folder importable.
# This expects agent/, cards/, collector/ and demo_ui/ to sit side by side.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "agent"))
import identify_api  # Tiana's single entry point to the identifier

# Where the collected chatbot answers live (used to simulate a company chatbot)
RAW = ROOT / "collector" / "data" / "raw"

# Where registered chatbots (baselines) are saved by `check_chatbot.py register`
DEPLOYMENTS = ROOT / "agent" / "deployments"


# ---------------------------------------------------------------------------
# 1. Get the 6 probe questions (LM-01, LM-05, LM-06, I1, I2, V1-15)
#    Returns {probe_id: question_text}
# ---------------------------------------------------------------------------
def get_questions():
    return identify_api.get_probes()


# ---------------------------------------------------------------------------
# 2. Send the chatbot's answers to the real system and return its result.
#    test_mode=True  -> fake judge (no API calls, no cost)
#    test_mode=False -> real judge (Gemini, needs GEMINI_API_KEY in collector/.env)
#    deployment      -> name of a registered chatbot; if given, the system
#                       also checks for drift (model swapped).
#    Returns a dict: status, identified, fit_score, handoff_to_next_method,
#    reasons, card, judge, answers.
# ---------------------------------------------------------------------------
def run_check(answers, domain, deployment=None, test_mode=True):
    return identify_api.identify(
        answers,
        domain=domain,
        deployment=deployment or None,
        judge_provider="mock" if test_mode else "google",
    )


# ---------------------------------------------------------------------------
# 3. CHANGED: the dropdown now lists all 11 models the system knows
#    (before it only had 3). Names on the left are what the user sees,
#    keys on the right are the folder names in collector/data/raw/.
#    The keys come from Tiana's run_all_tests.sh -- if a folder name in
#    your repo is different, fix it here.
# ---------------------------------------------------------------------------
VERSION_TO_KEY = {
    "Llama 3.1 8B": "llama3.1-8b",
    "Llama 3.2 3B": "llama3.2-3b",
    "Qwen3 8B": "qwen3-8b",
    "Qwen3.5 9B": "qwen3.5-9b",
    "Gemma 3 4B": "gemma3-4b",
    "Gemini 3.8 Flash": "gemini-3.8-flash",
    "Gemini 3.1 Pro": "gemini-3.1-pro",
    "Claude Sonnet 5.5": "claude-sonnet-5.5",
    "Claude Haiku 4.5": "claude-haiku-4.5",
    "GPT-5.6 Terra": "gpt-5.6-terra",
    "GPT-5.6 Luna": "gpt-5.6-luna",
}

# NEW: models the system has NEVER seen. Good for demoing the "Unknown version"
# result. These key names are guesses (taken from check_chatbot.py), so check
# them against the folders in collector/data/raw/ and ask Tiana if unsure.
NEW_MODEL_TO_KEY = {
    "Claude Haiku 5.5 (new, never seen)": "claude-haiku-5-5",
    "GPT-6.1 Terra (new, never seen)": "gpt-6.1-terra",
    "GPT-6 Luna (new, never seen)": "gpt-6-luna",
}


def available_models():
    """NEW: only show models that actually have collected data on this computer.
    If the data folder isn't there at all, show everything so the page still loads."""
    everything = {**VERSION_TO_KEY, **NEW_MODEL_TO_KEY}
    found = {label: key for label, key in everything.items() if (RAW / key).exists()}
    return found or everything


# ---------------------------------------------------------------------------
# 4. Old helper: picks one random collected answer from a model's data.
#    The page doesn't use it any more -- safe to delete.
# ---------------------------------------------------------------------------
def sample_answer(model_key):
    rows = []
    for f in sorted((RAW / model_key).glob("*.jsonl")):
        with open(f) as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    if r.get("response_text") and not r.get("error"):
                        rows.append(r)
    return random.choice(rows)["response_text"] if rows else ""


# ---------------------------------------------------------------------------
# 5. Pretend to be a company chatbot: return {probe_id: answer} for the 6
#    probe questions, taken from one model's collected data.
#    CHANGED: we now pass a persona (BK1 = a bank system prompt) so all 6
#    answers come from the same "chatbot". Before, it grabbed the first answer
#    it found for each question, which could mix personas.
#    The persona should match the one used when registering a chatbot
#    for the drift check (step 6 below).
# ---------------------------------------------------------------------------
def collected_answers(model_key, persona=None):
    wanted = set(get_questions())
    found = {}
    for f in sorted((RAW / model_key).glob("*.jsonl")):
        with open(f) as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                pid = r.get("prompt_id")
                text = r.get("response_text")
                # keep only: a probe question we need, not already found,
                # with a real answer and no error
                if pid in wanted and pid not in found and text and not r.get("error"):
                    # skip answers from other personas
                    if persona and r.get("persona_id") != persona:
                        continue
                    found[pid] = text
    return found


# ---------------------------------------------------------------------------
# 6. NEW: list the chatbots that have been registered for the drift check.
#    Registering is done once from the agent/ folder, e.g.:
#      python check_chatbot.py register --deployment northshore \
#             --model llama3.1-8b --persona BK1 --replay
#    That creates agent/deployments/northshore.json, which shows up here.
# ---------------------------------------------------------------------------
def list_deployments():
    if not DEPLOYMENTS.exists():
        return []
    return sorted(p.stem for p in DEPLOYMENTS.glob("*.json"))


# ---------------------------------------------------------------------------
# 7. NEW: register a chatbot (used by the "Register a chatbot" page).
#    This runs the same command you would type by hand:
#      python check_chatbot.py register --deployment NAME --model KEY --persona BK1 --replay
#    from the agent/ folder. --replay uses our collected answers (free, no
#    API calls), so the persona must be one that has collected data (BK1-BK4).
#    Returns (True/False, message to show the user).
# ---------------------------------------------------------------------------
REGISTER_PERSONAS = ["BK1", "BK2", "BK3", "BK4"]


def register_chatbot(name, model_key, persona="BK1"):
    name = (name or "").strip()
    # Only letters, numbers, dashes and underscores: the name becomes a file name
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
        return False, "Use 1 to 40 letters, numbers, dashes or underscores for the name."
    command = [sys.executable, "check_chatbot.py", "register", "--deployment", name,
               "--model", model_key, "--persona", persona, "--replay"]
    try:
        done = subprocess.run(command, cwd=ROOT / "agent", capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False, "Registering took too long and was stopped. Try again."
    output = ((done.stdout or "") + (done.stderr or "")).strip()
    if done.returncode != 0 or not (DEPLOYMENTS / f"{name}.json").exists():
        return False, output or "Registering failed with no message."
    return True, output