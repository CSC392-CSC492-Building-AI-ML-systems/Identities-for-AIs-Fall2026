"""
Tests for the demo UI (backend.py and app.py).

What these tests are for
------------------------
They check that the UI sends the right things TO the system and shows the right
things BACK from it. 

Three kinds of test, from cheapest to most real:
  A. Plumbing tests   - free, no data needed. The UI passes information through correctly.
  B. Offline tests    - free, need collected data. The real code runs, but the judge is
                        replaced by a fixed answer, so the results are repeatable.
  C. Live tests       - cost a few cents, need GEMINI_API_KEY. The real judge runs, so these
                        show the whole thing works for real. Marked "live".

How to run (from the demo_ui/ folder, with the same Python environment as the app):
    pip install pytest
    python -m pytest test_ui.py -v                 # A and B, plus C if GEMINI_API_KEY is set
    python -m pytest test_ui.py -v -m "not live"   # skip the live tests (free)
    python -m pytest test_ui.py -v -m live         # only the live tests

Tests that need collected data skip themselves (they do not fail) if the data is missing.
"""
import json
import os
from pathlib import Path

import pytest

import backend                              # also puts agent/ on the path and loads collector/.env
import check_chatbot
import identify_api
from identify import DEVELOPER, MODELS
from probe_identify import DEFAULT_PROBES

PERSONA = "BK1"                             # the persona the demo uses (DEMO_PERSONA in app.py)
HAVE_KEY = bool(os.environ.get("GEMINI_API_KEY"))
live = pytest.mark.skipif(not HAVE_KEY, reason="needs GEMINI_API_KEY in collector/.env")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def answers_for(key):
    """The answers the UI would load for a model. Skips the test if there is no data."""
    if not (backend.RAW / key).exists():
        pytest.skip(f"no collected data for {key}")
    answers = backend.collected_answers(key, persona=PERSONA)
    if len(answers) < 3:
        pytest.skip(f"fewer than 3 {PERSONA} answers for {key}")
    return answers


def use_fixed_judge(monkeypatch, key):
    """Replace the judge with a fixed answer ('this is model KEY'). Same trick Tiana's own
    test_rules.py uses. Her rules and checks still run on top of it."""
    family, version = MODELS[key]
    reply = json.dumps({"family": family, "version": version, "family_confidence": 0.9,
                        "version_confidence": 0.9, "reason": "fixed judge for testing"})
    monkeypatch.setattr(check_chatbot, "call_llm", lambda *a, **k: reply)


# ===========================================================================
# A. PLUMBING TESTS (free, no data needed)
# ===========================================================================
def test_ui_asks_the_same_questions_as_the_system():
    """PROVES: the six questions on the page are exactly the ones Tiana's system uses,
    and they are the six we expect. If these differed, the chatbot would be asked the
    wrong questions and the identification would be meaningless."""
    assert backend.get_questions() == identify_api.get_probes()
    assert set(backend.get_questions()) == set(DEFAULT_PROBES)
    assert len(backend.get_questions()) == 6


def test_run_check_forwards_everything_to_the_system(monkeypatch):
    """PROVES: what you type or pick on the page (answers, domain, approved chatbot, test mode)
    reaches Tiana's identify() unchanged, and her result comes back untouched.
    Her function is replaced by a recorder, so nothing real runs."""
    seen = {}

    def recorder(answers, domain=None, deployment=None, judge_provider="google", **kw):
        seen.update(answers=answers, domain=domain, deployment=deployment, judge=judge_provider)
        return {"marker": "result from the system"}

    monkeypatch.setattr(identify_api, "identify", recorder)
    out = backend.run_check({"I1": "hello"}, "risk", "northshore", test_mode=True)
    assert seen == {"answers": {"I1": "hello"}, "domain": "risk", "deployment": "northshore", "judge": "mock"}
    assert out == {"marker": "result from the system"}      # nothing added, removed or changed


def test_test_mode_switch_picks_the_right_judge(monkeypatch):
    """PROVES: ticking 'Test mode' uses the fake judge (free) and unticking it uses the real
    Gemini judge. Also that an empty approved-chatbot choice means 'no drift check'.
    A mix-up here would either cost money by accident or show fake results as real."""
    seen = {}
    monkeypatch.setattr(identify_api, "identify",
                        lambda answers, domain=None, deployment=None, judge_provider="google", **kw:
                        seen.update(judge=judge_provider, deployment=deployment) or {})
    backend.run_check({}, "risk", "", test_mode=True)
    assert seen == {"judge": "mock", "deployment": None}
    backend.run_check({}, "risk", "", test_mode=False)
    assert seen["judge"] == "google"


def test_dropdown_models_are_models_the_system_knows():
    """PROVES: every model in the dropdown is a model Tiana's system has data and cards for.
    The 'never seen' models must NOT be known to the system, otherwise the 'Unknown version'
    demo would not be a real test. (If Tiana adds one of them to the system, update
    NEW_MODEL_TO_KEY.)"""
    for label, key in backend.VERSION_TO_KEY.items():
        assert key in MODELS, f"{label}: '{key}' is not a model key in identify.MODELS"
    for label, key in backend.NEW_MODEL_TO_KEY.items():
        assert key not in MODELS, f"{label}: '{key}' is already known, so it is not a 'new' model"
    assert backend.available_models()          # the dropdown is never empty


def test_every_status_the_system_can_return_is_handled_by_the_page():
    """PROVES: the page has a message and a colour for every status Tiana's system can return
    (see her WRITEUP). Otherwise a real status would show with no explanation."""
    source = (Path(__file__).parent / "app.py").read_text(encoding="utf-8")
    for status in ["Verified", "Identified", "Drift detected", "Needs review", "Unknown model"]:
        assert f'"{status}"' in source, f"app.py does not handle the status '{status}'"


def test_register_rejects_bad_names_without_running_anything(monkeypatch):
    """PROVES: the Register page refuses names that could break things (empty, spaces, path
    tricks like '../', too long). The name becomes a file name, so this protects the repo.
    subprocess.run is replaced with an error, so the test also proves nothing was run."""
    def boom(*a, **k):
        raise AssertionError("the command ran for a bad name")
    monkeypatch.setattr(backend.subprocess, "run", boom)
    for bad in ["", "   ", "../evil", "has space", "semi;colon", "x" * 41]:
        ok, message = backend.register_chatbot(bad, "llama3.1-8b", "BK1")
        assert ok is False and message


def test_registered_chatbot_list_matches_the_files(monkeypatch, tmp_path):
    """PROVES: the 'Approved chatbot' dropdown lists exactly the registered chatbots
    (the .json files in agent/deployments), and is empty when there are none."""
    monkeypatch.setattr(backend, "DEPLOYMENTS", tmp_path / "missing")
    assert backend.list_deployments() == []
    monkeypatch.setattr(backend, "DEPLOYMENTS", tmp_path)
    (tmp_path / "beta.json").write_text("{}")
    (tmp_path / "alpha.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("ignore me")
    assert backend.list_deployments() == ["alpha", "beta"]


# ===========================================================================
# B. OFFLINE TESTS (free, need the collected data; judge replaced by a fixed answer)
# ===========================================================================
def test_loaded_answers_really_come_from_that_models_data():
    """PROVES: clicking 'Ask the chatbot six questions' loads real collected answers from the
    chosen model's file, for the right persona. Every answer on the page is found word for
    word in collector/data/raw/<model>/. Nothing is made up or taken from another model."""
    key = "llama3.1-8b"
    answers = answers_for(key)
    stored = set()
    for f in (backend.RAW / key).glob("*.jsonl"):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if r.get("persona_id") == PERSONA and r.get("response_text") and not r.get("error"):
                    stored.add(r["response_text"])
    assert set(answers) <= set(backend.get_questions())     # only real probe ids
    for pid, text in answers.items():
        assert text in stored, f"{pid}: this answer is not in {key}'s data"


def test_different_models_load_different_answers():
    """PROVES: picking a different model in the dropdown really loads different answers
    (the model choice is not ignored, and answers are not mixed between models)."""
    a = answers_for("llama3.1-8b")
    b = answers_for("qwen3-8b")
    assert a != b
    assert any(a[p] != b[p] for p in set(a) & set(b))


@pytest.mark.parametrize("key", ["llama3.1-8b", "qwen3-8b", "gemma3-4b"])
def test_system_result_has_everything_the_page_shows(monkeypatch, key):
    """PROVES: for real collected answers, Tiana's system returns every field the page draws
    (status, developer, family, version, fit score, card), the developer is the right company
    for that model, and the fit score is between 0 and 1 (the bar on the page needs that).
    The judge is fixed, so this checks the code around it (name detector, rules, cards)."""
    answers = answers_for(key)
    use_fixed_judge(monkeypatch, key)
    res = backend.run_check(answers, "compliance", None, test_mode=True)
    for field in ["status", "identified", "fit_score", "reasons", "card", "handoff_to_next_method"]:
        assert field in res, f"result is missing '{field}'"
    for field in ["developer", "family", "version"]:
        assert field in res["identified"]
    assert res["identified"]["developer"] == DEVELOPER[MODELS[key][0]]
    assert 0 <= res["fit_score"] <= 1
    assert res["status"] in ("Identified", "Unknown model")      # no approved chatbot, so no Verified/Drift


def test_model_card_has_the_shape_the_page_expects(monkeypatch):
    """PROVES: the card Tiana returns has the structure show_card() in app.py reads, so the page
    cannot crash on it. Every field has either a single 'value' (exact model card) or a list of
    'values' (family or developer card), each saying which models it came from."""
    key = "llama3.1-8b"
    answers = answers_for(key)
    use_fixed_judge(monkeypatch, key)
    card = backend.run_check(answers, "compliance", None, test_mode=True)["card"]
    assert card["level"] in ("version", "family", "developer", "none")
    for domain in card["domains"]:
        assert domain.get("title") or domain.get("domain")
        for f in domain["fields"]:
            assert "value" in f or "values" in f
            for v in f.get("values", []):
                assert v["from_models"]


def test_domain_choice_changes_the_card(monkeypatch):
    """PROVES: the 'Model card view' setting really reaches the system. Choosing 'risk' gives
    the risk card, not a different domain's."""
    key = "llama3.1-8b"
    answers = answers_for(key)
    use_fixed_judge(monkeypatch, key)
    card = backend.run_check(answers, "risk", None, test_mode=True)["card"]
    assert [d["domain"] for d in card["domains"]] == ["risk"]


@pytest.fixture
def approved_chatbot():
    """Registers a temporary approved chatbot (Llama 3.1 8B under the BK1 prompt) using the same
    function as the Register page, then deletes it afterwards so the demo list stays clean."""
    answers_for("llama3.1-8b")                                  # skip if no data
    name = "pytest-temp-chatbot"
    ok, message = backend.register_chatbot(name, "llama3.1-8b", PERSONA)
    assert ok, f"registering failed: {message}"
    yield name
    (backend.DEPLOYMENTS / f"{name}.json").unlink(missing_ok=True)


def test_register_page_creates_a_usable_chatbot(approved_chatbot):
    """PROVES: the Register page really works. The chatbot is saved, appears in the sidebar
    list, and its saved record names the model we picked and contains answers to the probes."""
    assert approved_chatbot in backend.list_deployments()
    record = json.loads((backend.DEPLOYMENTS / f"{approved_chatbot}.json").read_text(encoding="utf-8"))
    assert record["baseline"]                                   # the saved answers to the probes
    assert record["approved_model"] == "llama3.1-8b"


def test_no_swap_is_not_reported_as_drift(monkeypatch, approved_chatbot):
    """PROVES: when the model behind the chatbot has NOT changed, the page does not cry
    'Drift detected' (no false alarm). The judge is fixed to the true model."""
    answers = answers_for("llama3.1-8b")
    use_fixed_judge(monkeypatch, "llama3.1-8b")
    res = backend.run_check(answers, "compliance", approved_chatbot, test_mode=True)
    assert res["status"] in ("Verified", "Needs review")
    assert res["approved_model"] == MODELS["llama3.1-8b"][1]


def test_a_swapped_model_is_reported_as_drift(monkeypatch, approved_chatbot):
    """PROVES: when the answers come from a DIFFERENT model than the approved one (a silent
    swap), the page shows 'Drift detected', and the system names the right developer for the
    new model. This is the main demo scenario."""
    answers = answers_for("qwen3-8b")
    use_fixed_judge(monkeypatch, "qwen3-8b")
    res = backend.run_check(answers, "compliance", approved_chatbot, test_mode=True)
    assert res["status"] == "Drift detected"
    assert res["identified"]["developer"] == DEVELOPER[MODELS["qwen3-8b"][0]]


# ===========================================================================
# C. LIVE TESTS (real Gemini judge, cost a few cents, need GEMINI_API_KEY)
# These use the real judge, so results can vary a little between runs. The limits below
# are loose on purpose and match Tiana's WRITEUP (developer 99% right, version 81% right).
# ===========================================================================
@live
@pytest.mark.parametrize("key", ["llama3.1-8b", "qwen3-8b", "gemma3-4b", "gemini-3.8-flash", "claude-haiku-4.5"])
def test_live_developer_is_right_for_known_models(key):
    """PROVES: end to end with the real judge, the page names the right DEVELOPER for models the
    system knows. Developer is the most reliable output (99% in Tiana's tests), so a miss here
    points to a real problem, such as wrong answers being loaded or a wrong API key."""
    answers = answers_for(key)
    res = backend.run_check(answers, "compliance", None, test_mode=False)
    assert res["identified"]["developer"] == DEVELOPER[MODELS[key][0]], res["reasons"]


@live
def test_live_most_known_models_get_the_exact_version():
    """PROVES: the exact version is right for most known models. Tiana measured 81%, so we ask
    for at least half of this small set (a single miss is normal, since the judge varies)."""
    keys = ["llama3.1-8b", "qwen3-8b", "gemma3-4b", "gemini-3.8-flash", "claude-haiku-4.5", "gemini-3.1-pro"]
    right = 0
    tried = 0
    for key in keys:
        if not (backend.RAW / key).exists():
            continue
        answers = backend.collected_answers(key, persona=PERSONA)
        if len(answers) < 3:
            continue
        tried += 1
        res = backend.run_check(answers, "compliance", None, test_mode=False)
        right += res["identified"]["version"] == MODELS[key][1]
    if tried < 3:
        pytest.skip("not enough models with data to judge")
    assert right / tried >= 0.5, f"only {right} of {tried} versions were right"


@live
def test_live_swap_is_detected(approved_chatbot):
    """PROVES: the full demo works with the real judge. Register Llama 3.1 8B, then feed answers
    from Qwen3 8B, and the system says 'Drift detected'. Tiana caught 97% of swaps, so a rare
    miss is possible. Run it again before concluding something is broken."""
    answers = answers_for("qwen3-8b")
    res = backend.run_check(answers, "compliance", approved_chatbot, test_mode=False)
    assert res["status"] == "Drift detected", res["reasons"]


@live
def test_live_new_model_gets_unknown_version():
    """PROVES: a model the system has never seen is NOT forced into a wrong known version. The
    version should be 'Unknown' and the developer right (Tiana: 23 of 24 never-seen chatbots).
    Skips if the never-seen models' data is not in the repo."""
    key = backend.NEW_MODEL_TO_KEY["Claude Haiku 5.5 (new, never seen)"]
    answers = answers_for(key)
    res = backend.run_check(answers, "compliance", None, test_mode=False)
    assert res["identified"]["developer"] == "Anthropic"
    assert res["identified"]["version"] == "Unknown", res["reasons"]