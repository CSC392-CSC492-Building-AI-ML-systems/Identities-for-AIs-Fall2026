"""One entry point to the agentic identifier, for other code (the evaluation pipeline, the demo UI, the package).

Your application asks its chatbot the 6 probe questions, then passes the answers here:

    from identify_api import get_probes, identify

    questions = get_probes()                       # {"LM-01": "...", "LM-05": "...", ...}
    answers = {pid: my_chatbot(text) for pid, text in questions.items()}

    result = identify(answers, domain="compliance")                            # chatbot never registered
    result = identify(answers, domain="risk", deployment="northshore")         # check a registered chatbot

The result is a dict (JSON-ready):
    status            "Verified" / "Drift detected" / "Needs review" (registered chatbot)
                      or "Identified" / "Unknown model" (not registered)
    identified        developer, family, version (each can be "Unknown"), model_key, closest_known_version
    fit_score         share of answers that fit (0-1); handoff_to_next_method: True = ask LoRA / random forest
    reasons           why, in words
    card              the domain card at the most specific level known: version -> family -> developer -> none
    judge             the judge model's own answer (not used for decisions)

From the command line (answers as a JSON file {"LM-01": "...", ...}):
    python identify_api.py probes                                   # print the 6 questions as JSON
    python identify_api.py answers.json --domain compliance [--deployment northshore]
    python identify_api.py answers.json --judge-provider mock       # no API calls, for testing the plumbing

Registering a chatbot (recording its baseline) is done once with check_chatbot.py register.
Needs GEMINI_API_KEY in collector/.env for the judge (about $0.008 per call).
"""
import argparse, json, sys
from pathlib import Path
from types import SimpleNamespace

import check_chatbot
from identify import HERE, load_env, load_prompt_texts
from probe_identify import DEFAULT_PROBES, attach_card

DOMAINS = ["compliance", "governance", "evaluation", "risk"]
load_env(HERE.parent / "collector" / ".env")


def get_probes():
    """The 6 probe questions to send to the chatbot: probe id -> question text."""
    texts = {pid: t for (ds, pid), t in load_prompt_texts(["fingerprint"]).items() if pid in DEFAULT_PROBES}
    return {pid: texts[pid] for pid in DEFAULT_PROBES if pid in texts}


def identify(answers, domain=None, deployment=None, judge_provider="google", judge_model="gemini-3.8-flash",
             handoff_below=check_chatbot.HANDOFF_BELOW):
    """Identify the model behind a chatbot from its answers to the probes (probe id -> answer text).
    domain: one of compliance / governance / evaluation / risk (None = all four cards).
    deployment: name of a chatbot registered with check_chatbot.py register -> also checks for drift."""
    if domain is not None and domain not in DOMAINS:
        raise ValueError(f"domain must be one of {DOMAINS}")
    session = {pid: a for pid, a in (answers or {}).items() if pid in DEFAULT_PROBES and a and a.strip()}
    if len(session) < 3:
        raise ValueError(f"need answers to at least 3 of the probes {DEFAULT_PROBES}; got {sorted(session)}")
    args = SimpleNamespace(judge_provider=judge_provider, judge_model=judge_model, handoff_below=handoff_below)
    baseline = approved = None
    if deployment:
        path = check_chatbot.DEPLOYMENTS / f"{deployment}.json"
        if not path.exists():
            raise ValueError(f"'{deployment}' is not registered (run check_chatbot.py register first)")
        dep = json.loads(path.read_text(encoding="utf-8"))
        baseline, approved = dep["baseline"], dep["approved_model"]
    result = check_chatbot.identify_answers(session, args, baseline=baseline, approved=approved)
    if deployment:
        result = {"deployment": deployment, "approved_model": dep["approved_version"], **result}
    i = result["identified"]
    result["card"] = attach_card(domain, i["model_key"], i["family"], i["developer"])
    result["answers"] = session
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answers", help="'probes' to print the questions, or a JSON file of answers {probe id: answer}")
    ap.add_argument("--domain", choices=DOMAINS)
    ap.add_argument("--deployment", help="a chatbot registered with check_chatbot.py register")
    ap.add_argument("--judge-provider", default="google", choices=["google", "anthropic", "openai", "mock"])
    ap.add_argument("--judge-model", default="gemini-3.8-flash")
    args = ap.parse_args()
    if args.answers == "probes":
        print(json.dumps(get_probes(), indent=2, ensure_ascii=False))
        return
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    try:
        result = identify(answers, args.domain, args.deployment, args.judge_provider, args.judge_model)
    except ValueError as e:
        sys.exit(str(e))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()