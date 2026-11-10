"""Unit tests for the identifier's code checks: small made-up inputs with a known right answer.

    python test_rules.py            # runs every test, prints pass/fail, exit code 1 if any fail
    python -m pytest test_rules.py  # also works with pytest

No API calls and no collected data needed (except the last test, which uses the cards folder).
"""
import json
import sys

import check_chatbot
import probe_identify as pi
from identify import MODELS

KNOWN = list(MODELS)


# --- name detector ----------------------------------------------------------------------------------------
def test_name_detector_finds_each_developer():
    assert pi.detect_names("I was created by Meta AI") == ["Meta"]
    assert pi.detect_names("I'm Qwen, from Alibaba Cloud") == ["Alibaba"]
    assert pi.detect_names("I am Gemini, a model by Google") == ["Google"]
    assert pi.detect_names("I'm Claude, made by Anthropic") == ["Anthropic"]
    assert pi.detect_names("I'm ChatGPT, powered by OpenAI") == ["OpenAI"]
    assert pi.detect_names("I'm your bank's assistant") == []


def test_name_evidence_needs_one_developer():
    _, dev = pi.name_evidence(["I was made by OpenAI", "I'm ChatGPT"])
    assert dev == "OpenAI"
    _, dev = pi.name_evidence(["I was made by OpenAI", "Built on Llama"])   # two developers named: no single answer
    assert dev is None


# --- self-name rule -----------------------------------------------------------------------------------------
def test_self_identifies():
    assert pi.self_identifies("I am Gemini 3.8 Flash, built by Google.", "Gemini Flash")
    assert not pi.self_identifies("I am Gemini, built by Google.", "Gemini Flash")
    assert not pi.self_identifies("Flash floods are dangerous.", "Gemini Flash")


# --- baseline misfits -------------------------------------------------------------------------------------
def test_baseline_misfits():
    base = {"LM-05": ["My knowledge cutoff is June 2024.", "My cutoff is June 2024."],
            "I1": ["I was created by OpenAI.", "I was created by OpenAI."],
            "V1-15": ["x" * 1000, "x" * 1200]}
    same = {"LM-05": "My knowledge cutoff is June 2024.", "I1": "I was created by OpenAI.", "V1-15": "x" * 1100}
    assert pi.baseline_misfits(same, base) == []
    other = {"LM-05": "My cutoff is December 2023.",            # a date the baseline never states
             "I1": "I can't share that.",                        # refuses where the baseline never does
             "V1-15": "x" * 300}                                 # far shorter than every baseline answer
    found = pi.baseline_misfits(other, base)
    assert any(f.startswith("LM-05") and "date" in f for f in found)
    assert any(f.startswith("I1") and "refusal" in f for f in found)
    assert any(f.startswith("V1-15") and "length" in f for f in found)


# --- apply_rules ------------------------------------------------------------------------------------------
PRED = {"family": "Llama", "version": "Llama 3.1 8B"}


def test_rules_keep_a_good_fit():
    final, rule = pi.apply_rules(PRED, "Meta", KNOWN, ["I2: length"], 3)
    assert final["version"] == "Llama 3.1 8B" and rule is None


def test_rules_three_misfits_make_version_unknown():
    final, rule = pi.apply_rules(PRED, "Meta", KNOWN, ["a", "b", "c"], 3)
    assert final["version"] == "Unknown" and final["family"] == "Llama" and "do not fit" in rule


def test_rules_unknown_developer_makes_family_unknown():
    final, _ = pi.apply_rules(PRED, "Mistral", ["llama3.1-8b"], [], 3)    # "Mistral" makes none of the known models
    assert final["family"] == "Unknown" and final["version"] == "Unknown"


def test_rules_self_name():
    pred = {"family": "Gemini Flash", "version": "Gemini 3.8 Flash"}
    final, _ = pi.apply_rules(pred, "Google", KNOWN, ["a", "b", "c"], 3, chatbot_self_id=False, model_self_id_rate=0.9)
    assert final["family"] == "Unknown"         # its line always names itself, this chatbot never does
    final, _ = pi.apply_rules(pred, "Google", KNOWN, ["a", "b", "c"], 3, chatbot_self_id=True, model_self_id_rate=0.9)
    assert final["family"] == "Gemini Flash"    # it does name itself: new version of the same line


# --- phrase check (sibling_check) -------------------------------------------------------------------------
def _recs(model, texts):
    return [{"model_key": model, "persona_id": p, "sample_index": s, "prompt_id": "I2", "response_text": t}
            for p, t in zip(["P01", "P12", "P13", "P15"], texts) for s in (0, 1)]


RECS = _recs("gpt-5.6-luna", ["I'm ChatGPT, powered by OpenAI today."] * 4) + \
       _recs("gpt-5.6-terra", ["I am an AI assistant accessed through an API."] * 4)


def test_sibling_check_switches_to_the_sibling():
    session = {"I2": "I am an AI assistant accessed through an API, sorry."}   # Terra's wording
    key, rule = pi.sibling_check(session, "gpt-5.6-luna", ["gpt-5.6-luna", "gpt-5.6-terra"], RECS, "BK1")
    assert key == "gpt-5.6-terra" and "switched" in rule


def test_sibling_check_keeps_the_judge_when_wording_fits():
    session = {"I2": "I'm ChatGPT, powered by OpenAI today."}                   # Luna's wording
    key, rule = pi.sibling_check(session, "gpt-5.6-luna", ["gpt-5.6-luna", "gpt-5.6-terra"], RECS, "BK1")
    assert key == "gpt-5.6-luna" and rule is None


def test_sibling_check_ignores_other_developers():
    session = {"I2": "I am an AI assistant accessed through an API."}
    key, _ = pi.sibling_check(session, "llama3.1-8b", ["llama3.1-8b", "gpt-5.6-terra"], RECS, "BK1")
    assert key == "llama3.1-8b"


# --- check_chatbot status (judge replaced by a fixed answer) -----------------------------------------------
class Args:
    judge_provider, judge_model, handoff_below = "mock", "mock", 0.7


def _check(judge_version, session, baseline, approved):
    fam = next(f for f, v in MODELS.values() if v == judge_version) if judge_version != "Unknown" else "Unknown"
    original = check_chatbot.call_llm
    check_chatbot.call_llm = lambda *a: json.dumps({"family": fam, "version": judge_version,
                                                    "family_confidence": 0.9, "version_confidence": 0.9, "reason": "test"})
    try:
        return check_chatbot.identify_answers(session, Args, baseline=baseline, approved=approved)
    finally:
        check_chatbot.call_llm = original


BASE = {"LM-05": ["My knowledge cutoff is December 2023."] * 2, "I1": ["I was created by Meta."] * 2,
        "I2": ["I'm a Llama model by Meta."] * 2, "LM-01": ["I was created by Meta."] * 2}


def test_status_verified_when_nothing_changed():
    session = {p: v[0] for p, v in BASE.items()}
    res = _check("Llama 3.1 8B", session, BASE, "llama3.1-8b")
    assert res["status"] == "Verified", res


def test_status_drift_when_answers_change():
    session = {"LM-05": "My cutoff is October 2024.", "I1": "I am Qwen, created by Alibaba Cloud.",
               "I2": "I am Qwen3, by Alibaba Cloud.", "LM-01": "I am Qwen, created by Alibaba Cloud."}
    res = _check("Qwen3 8B", session, BASE, "llama3.1-8b")
    assert res["status"] == "Drift detected", res


# --- cards --------------------------------------------------------------------------------------------------
def test_card_levels():
    from card_lookup import lookup_card
    assert lookup_card(version_key="qwen3-8b")["level"] == "version"
    assert lookup_card(family="Llama")["level"] == "family"
    assert lookup_card(family="Gemma")["level"] == "developer"          # only one known Gemma version
    assert lookup_card(developer="Anthropic")["level"] == "developer"
    assert lookup_card(family="Unknown", developer="Unknown")["level"] == "none"
    hidden = lookup_card(version_key="claude-haiku-4.5", family="Claude Haiku", developer="Anthropic",
                         known=[k for k in MODELS if k != "claude-haiku-4.5"])
    assert "claude-haiku-4.5" not in hidden["known_models"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"pass  {name}")
        except Exception as e:     # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__} {e}"[:300])
    print(f"\n{len(tests) - failed}/{len(tests)} unit tests passed")
    sys.exit(1 if failed else 0)