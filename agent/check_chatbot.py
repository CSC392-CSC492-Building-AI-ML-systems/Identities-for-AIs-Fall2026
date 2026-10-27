"""
Check a chatbot (Stage 2 in use): register a deployment's baseline, then check it later for model changes.

    # 1. Register: the bank's approved chatbot answers the 6 probes twice; the answers are saved as its baseline.
    python check_chatbot.py register --deployment bank-support --model llama3.1-8b --persona BK1

    # 2. Check: send the 6 probes again, identify the model, compare with the baseline, attach a card.
    python check_chatbot.py check --deployment bank-support --domain compliance

    # Simulate a vendor silently swapping the model behind the same chatbot (for demos and tests):
    python check_chatbot.py check --deployment bank-support --swap-to llama3.2-3b

    # Identify a chatbot that was never registered (no baseline; less reliable):
    python check_chatbot.py identify --model gemma3-4b --persona P13

A "chatbot" here is a model from collector/models.yaml plus a system prompt: a persona from
collector/prompts/personas.yaml (--persona) or your own text file (--system-prompt-file).
--replay takes the answers from our collected data instead of calling the model (free, for tests and demos):
register uses samples 0-1, check/identify use sample 2. Add --judge-provider mock to make no API calls at all.

Each check saves one JSON result in results/checks/ with: what the chatbot is now (developer, family, version,
"Unknown" allowed), a status (Verified / Drift detected / Needs review), the fit score, whether to hand off
to the next method in the pipeline, the reasons, and the domain card.
"""
import argparse, datetime, json, os, re, sys, time, urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

from identify import DEVELOPER, HERE, MODELS, call_llm, load_env, load_prompt_texts, load_records, parse
from probe_identify import (DEFAULT_PROBES, IDENTITY_PROBES, apply_rules, attach_card, baseline_misfits,
                            build_messages, code_misfits, name_evidence, self_id_rate, self_identifies)

COLLECTOR = HERE.parent / "collector"
DEPLOYMENTS = HERE / "deployments"           # one baseline file per registered deployment
CHECKS = HERE / "results" / "checks"         # one result file per check
TEMPERATURE, MAX_TOKENS = 0.7, 1200          # same settings as our data collection, so answers are comparable
BASELINE_SAMPLES = 2
HANDOFF_BELOW = 0.7                          # fit score below this -> pass to the next method (LoRA, then RF)
MAX_MISFIT = 3
CHAT_APIS = {   # OpenAI-compatible chat endpoints and the .env key each needs
    "ollama":    ("http://localhost:11434/v1", None),
    "google":    ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "openai":    ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}


# --- Talking to the chatbot ------------------------------------------------------------------------------
def model_entry(model_key):
    for m in yaml.safe_load(open(COLLECTOR / "models.yaml", encoding="utf-8"))["models"]:
        if m["model_key"] == model_key:
            return m
    exit(f"'{model_key}' is not in collector/models.yaml")


def system_prompt(args):
    if args.system_prompt_file:
        return Path(args.system_prompt_file).read_text(encoding="utf-8"), Path(args.system_prompt_file).name
    personas = {p["id"]: p.get("text") or "" for p in
                yaml.safe_load(open(COLLECTOR / "prompts" / "personas.yaml", encoding="utf-8"))["personas"]}
    if args.persona not in personas:
        exit(f"Persona '{args.persona}' is not in collector/prompts/personas.yaml")
    return personas[args.persona], args.persona


def ask_chatbot(model_key, system, question):
    """One question to the chatbot. Thinking text (<think>...</think>) is removed, as in the collector."""
    m = model_entry(model_key)
    base, key_env = CHAT_APIS[m["provider"]]
    headers = {"Content-Type": "application/json"}
    if key_env:
        key = os.environ.get(key_env) or exit(f"Set {key_env} in collector/.env")
        headers["Authorization"] = f"Bearer {key}"
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": question}]
    body = json.dumps({"model": m["model_id"], "messages": messages,
                       "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as r:
        text = json.load(r)["choices"][0]["message"].get("content") or ""
    if m.get("delay_seconds"):
        time.sleep(m["delay_seconds"])
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def replay_answers(model_key, persona, samples):
    """Answers from our collected data instead of a live call: probe -> list of answers."""
    out = defaultdict(list)
    for r in load_records({model_key: MODELS[model_key]}, ["fingerprint"]):
        if r["persona_id"] == persona and r["sample_index"] in samples and r["prompt_id"] in DEFAULT_PROBES:
            out[r["prompt_id"]].append(r["response_text"])
    if not out:
        exit(f"No collected answers for {model_key} under {persona}")
    return out


def get_answers(args, model_key, system, persona_label, samples, n):
    if args.replay:
        if getattr(args, "system_prompt_file", None):
            exit("--replay only works with --persona (our data uses those system prompts)")
        return replay_answers(model_key, persona_label, samples)
    questions = {pid: t for (ds, pid), t in load_prompt_texts(["fingerprint"]).items() if pid in DEFAULT_PROBES}
    out = defaultdict(list)
    for pid in DEFAULT_PROBES:
        for _ in range(n):
            out[pid].append(ask_chatbot(model_key, system, questions[pid]))
            print(f"  {pid}: {out[pid][-1][:80]!r}")
    return out


# --- Identifying ----------------------------------------------------------------------------------------
def identify_answers(session, args, baseline=None, approved=None):
    """Judge the answers, then apply the code checks. Returns the result dict (without card)."""
    recs = [r for r in load_records(MODELS, ["fingerprint"]) if r["prompt_id"] in DEFAULT_PROBES]
    known = sorted({r["model_key"] for r in recs})
    refs = {k: defaultdict(list) for k in known}
    for r in recs:
        if r["sample_index"] in (0, 1):
            refs[r["model_key"]][r["prompt_id"]].append(r["response_text"])
    prompt_text = {pid: t for (ds, pid), t in load_prompt_texts(["fingerprint"]).items()}
    pred = parse(call_llm(args.judge_provider, args.judge_model, build_messages(session, refs, known, DEFAULT_PROBES, prompt_text)))

    judge_key = next((k for k in known if MODELS[k][1] == pred.get("version")), None)
    _, names_dev = name_evidence(list(session.values()))
    # 1. Drift: does the chatbot still behave like the approved model's baseline? (registered deployments only)
    drift = baseline_misfits(session, baseline) if baseline is not None else None
    # 2. Identity: does it really fit the model the judge chose? If the judge chose the approved model, its own
    #    baseline is the best reference (a new version of the same model shows up as drift). If the judge chose
    #    another model, compare with that model's answers in our data.
    if drift is not None and judge_key == approved:
        misfits = drift
    else:
        misfits = code_misfits(session, refs[judge_key]) if judge_key else None
    fam = pred.get("family") or "Unknown"
    chatbot_self_id = any(self_identifies(session.get(p), fam) for p in IDENTITY_PROBES) if judge_key else None
    rate = self_id_rate(recs, judge_key, None, fam) if judge_key else 0.0
    final, rule = apply_rules(pred, names_dev, known, misfits, MAX_MISFIT, chatbot_self_id, rate)
    if final.get("version") not in [MODELS[k][1] for k in known]:   # the judge named a model we have no data for
        final["version"] = "Unknown"
    fit = round(1 - len(misfits) / len(session), 2) if misfits is not None else None
    key = next((k for k in known if MODELS[k][1] == final.get("version")), None)

    if drift is None:
        status = "Identified" if key else "Unknown model"
    elif len(drift) >= MAX_MISFIT or (key and key != approved):
        status = "Drift detected"            # no longer behaves like the approved model, or is now another model
    elif key == approved:
        status = "Verified"
    else:
        status = "Needs review"
    handoff = final.get("version") == "Unknown" or fit is None or fit < args.handoff_below
    if status == "Verified" and handoff:
        status = "Needs review"
    reasons = [x for x in [rule, pred.get("reason")] if x]
    if drift is not None:
        reasons.append(f"{len(drift)} of {len(session)} probes differ from the approved model's baseline"
                       + (f": {', '.join(drift)}" if drift else ""))
    if misfits is not drift and misfits:
        reasons.append(f"does not fit {pred.get('version')}: {', '.join(misfits)}")
    return {"identified": {"developer": DEVELOPER.get(final.get("family")) or names_dev or "Unknown",
                           "family": final.get("family"), "version": final.get("version"), "model_key": key},
            "status": status, "fit_score": fit, "handoff_to_next_method": handoff,
            "names_developer": names_dev, "reasons": reasons,
            "judge": {k: pred.get(k) for k in ("family", "version", "family_confidence", "version_confidence")}}


# --- Commands -------------------------------------------------------------------------------------------
def cmd_register(args):
    system, label = system_prompt(args)
    print(f"Registering '{args.deployment}': {args.model} with system prompt {label}")
    answers = get_answers(args, args.model, system, label, (0, 1), BASELINE_SAMPLES)
    DEPLOYMENTS.mkdir(parents=True, exist_ok=True)
    record = {"deployment": args.deployment, "approved_model": args.model,
              "approved_version": MODELS[args.model][1], "system_prompt_label": label, "system_prompt": system,
              "probes": DEFAULT_PROBES, "baseline": answers, "replay": args.replay,
              "settings": {"temperature": TEMPERATURE, "max_tokens": MAX_TOKENS},
              "registered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    path = DEPLOYMENTS / f"{args.deployment}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved baseline -> {path}")


def save_and_print(result, name):
    CHECKS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path, n = CHECKS / f"{name}_{stamp}.json", 1
    while path.exists():                      # two checks in the same second
        n += 1
        path = CHECKS / f"{name}_{stamp}-{n}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    i = result["identified"]
    print(f"\nStatus: {result['status']}")
    print(f"Identified: {i['developer']} | family {i['family']} | version {i['version']} | fit {result['fit_score']}"
          + (" | hand off to next method" if result["handoff_to_next_method"] else ""))
    for r in result["reasons"]:
        print(f"  - {r}")
    print(f"Saved -> {path}")


def cmd_check(args):
    path = DEPLOYMENTS / f"{args.deployment}.json"
    if not path.exists():
        exit(f"'{args.deployment}' is not registered. Run: python check_chatbot.py register ...")
    dep = json.loads(path.read_text(encoding="utf-8"))
    serving = args.swap_to or dep["approved_model"]
    print(f"Checking '{args.deployment}' (approved: {dep['approved_version']})"
          + (f" -- simulating a swap to {MODELS[serving][1]}" if args.swap_to else ""))
    answers = get_answers(args, serving, dep["system_prompt"], dep["system_prompt_label"], (2,), 1)
    session = {pid: a[0] for pid, a in answers.items() if a and a[0]}
    result = identify_answers(session, args, baseline=dep["baseline"], approved=dep["approved_model"])
    result = {"deployment": args.deployment, "approved_model": dep["approved_version"],
              "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "simulated_swap_to": MODELS[serving][1] if args.swap_to else None, **result, "answers": session}
    if args.domain:
        i = result["identified"]
        result["card"] = attach_card(args.domain, i["model_key"], i["family"])
    save_and_print(result, args.deployment)


def cmd_identify(args):
    system, label = system_prompt(args)
    print(f"Identifying {args.model} with system prompt {label} (no baseline)")
    answers = get_answers(args, args.model, system, label, (2,), 1)
    session = {pid: a[0] for pid, a in answers.items() if a and a[0]}
    result = {"checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "true_model": MODELS[args.model][1], **identify_answers(session, args), "answers": session}
    if args.domain:
        i = result["identified"]
        result["card"] = attach_card(args.domain, i["model_key"], i["family"])
    save_and_print(result, f"identify_{args.model}_{label}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("register", "check", "identify"):
        p = sub.add_parser(name)
        p.add_argument("--replay", action="store_true", help="use our collected answers instead of calling the model")
        p.add_argument("--judge-provider", default="google", choices=["google", "anthropic", "openai", "mock"])
        p.add_argument("--judge-model", default="gemini-3.8-flash")
        p.add_argument("--handoff-below", type=float, default=HANDOFF_BELOW)
        if name in ("register", "check"):
            p.add_argument("--deployment", required=True, help="a name for the bank's chatbot, e.g. bank-support")
        if name in ("register", "identify"):
            p.add_argument("--model", required=True, choices=list(MODELS), help="the model behind the chatbot")
            p.add_argument("--persona", default="P13", help="system prompt from personas.yaml (P13 = none)")
            p.add_argument("--system-prompt-file", help="or a text file with your own system prompt")
        if name in ("check", "identify"):
            p.add_argument("--domain", choices=["compliance", "governance", "evaluation", "risk"],
                           help="attach this domain card to the result")
        if name == "check":
            p.add_argument("--swap-to", choices=list(MODELS), help="simulate the vendor swapping to this model")
    args = ap.parse_args()
    load_env(COLLECTOR / ".env")
    {"register": cmd_register, "check": cmd_check, "identify": cmd_identify}[args.command](args)


if __name__ == "__main__":
    main()