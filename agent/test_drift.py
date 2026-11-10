"""Automated drift test for check_chatbot.py: does a registered chatbot get flagged when its model is swapped?

For every approved model and bank persona, the chatbot is "registered" with its sample 0-1 answers (the
baseline), then checked with the sample-2 answers of every model under the same persona: the approved model
itself (no swap) and each other model (a silent swap). This is exactly what `check_chatbot.py check
--swap-to X --replay` does, for all pairs at once.

    python test_drift.py                                  # 11 models x 11 serving models x BK1-BK4 (~480 judge calls)
    python test_drift.py --models llama3.1-8b,qwen3-8b --personas BK1     # a small run
    python test_drift.py --judge-provider mock --out results/drift_mock.jsonl   # check it runs, no API calls

Graded per check:
  no swap: "Verified" = right | "Needs review" = soft alarm | "Drift detected" = false alarm
  swap:    "Drift detected" = caught | "Needs review" = flagged for review | "Verified" = missed
  and for swaps: was the new model identified (version), or at least its developer?

Results go to results/drift_test.jsonl (one line per check; running again continues the file).
"""
import argparse, json, time
from collections import Counter, defaultdict
from pathlib import Path

import check_chatbot
from identify import DEVELOPER, HERE, MODELS, load_env, load_records
from probe_identify import DEFAULT_PROBES

_RECS = None


def cached_records(models, datasets):
    """check_chatbot reloads all the data on every check; load it once instead."""
    global _RECS
    if _RECS is None:
        _RECS = load_records(MODELS, ["fingerprint"])
    return [r for r in _RECS if r["model_key"] in models]


check_chatbot.load_records = cached_records


def answers(model, persona, samples):
    out = defaultdict(list)
    for r in cached_records(MODELS, ["fingerprint"]):
        if r["model_key"] == model and r["persona_id"] == persona and r["sample_index"] in samples \
                and r["prompt_id"] in DEFAULT_PROBES:
            out[r["prompt_id"]].append(r["response_text"])
    return out


def relation(approved, serving):
    if approved == serving:
        return "no swap"
    if MODELS[approved][0] == MODELS[serving][0]:
        return "same line"
    if DEVELOPER[MODELS[approved][0]] == DEVELOPER[MODELS[serving][0]]:
        return "same developer"
    return "other developer"


def grade(row):
    s = row["status"]
    if row["relation"] == "no swap":
        return {"Verified": "right", "Needs review": "soft alarm", "Drift detected": "false alarm"}[s]
    return {"Drift detected": "caught", "Needs review": "flagged for review", "Verified": "missed"}[s]


def summary(rows):
    print(f"\n{len(rows)} checks")
    same = [r for r in rows if r["relation"] == "no swap"]
    swaps = [r for r in rows if r["relation"] != "no swap"]
    if same:
        c = Counter(r["outcome"] for r in same)
        print(f"No swap ({len(same)}): Verified {c['right']}, Needs review {c['soft alarm']}, "
              f"false alarm (Drift detected) {c['false alarm']}")
    if swaps:
        c = Counter(r["outcome"] for r in swaps)
        print(f"Swaps ({len(swaps)}): caught {c['caught']} ({100 * c['caught'] // len(swaps)}%), "
              f"flagged for review {c['flagged for review']}, missed {c['missed']}")
        print(f"  swapped model identified: version {sum(r['version_right'] for r in swaps)}/{len(swaps)}, "
              f"developer {sum(r['developer_right'] for r in swaps)}/{len(swaps)}")
        for rel in ("same line", "same developer", "other developer"):
            g = [r for r in swaps if r["relation"] == rel]
            if g:
                c = Counter(r["outcome"] for r in g)
                print(f"  {rel:16} {len(g):4}: caught {c['caught']}, review {c['flagged for review']}, missed {c['missed']}")
        missed = Counter((r["approved"], r["serving"]) for r in swaps if r["outcome"] == "missed")
        if missed:
            print("  missed swaps:", ", ".join(f"{a} -> {b} ({n})" for (a, b), n in missed.most_common(8)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", help="comma-separated approved models (default: all)")
    ap.add_argument("--serving", help="comma-separated models to swap in (default: all)")
    ap.add_argument("--personas", default="BK1,BK2,BK3,BK4")
    ap.add_argument("--judge-provider", default="google", choices=["google", "anthropic", "openai", "mock"])
    ap.add_argument("--judge-model", default="gemini-3.8-flash")
    ap.add_argument("--handoff-below", type=float, default=check_chatbot.HANDOFF_BELOW)
    ap.add_argument("--delay", type=float, default=1)
    ap.add_argument("--out", default=str(HERE / "results" / "drift_test.jsonl"))
    args = ap.parse_args()
    load_env(HERE.parent / "collector" / ".env")

    approved_list = args.models.split(",") if args.models else list(MODELS)
    serving_list = args.serving.split(",") if args.serving else list(MODELS)
    personas = args.personas.split(",")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if Path(args.out).exists():
        done = {(r["approved"], r["serving"], r["persona"]): r for r in map(json.loads, open(args.out, encoding="utf-8"))}
        print(f"Continuing: {len(done)} checks already in {args.out}")
    rows = [r for r in done.values() if r["approved"] in approved_list and r["serving"] in serving_list
            and r["persona"] in personas]
    jobs = [(a, s, p) for a in approved_list for p in personas for s in serving_list if (a, s, p) not in done]
    with open(args.out, "a", encoding="utf-8") as out:
        for i, (a, s, p) in enumerate(jobs, 1):
            baseline, session = answers(a, p, (0, 1)), answers(s, p, (2,))
            session = {pid: v[0] for pid, v in session.items() if v and v[0]}
            if len(session) < 3 or not baseline:
                print(f"[{i}/{len(jobs)}] skip {a} <- {s} {p}: not enough answers in our data")
                continue
            try:
                res = check_chatbot.identify_answers(session, args, baseline=dict(baseline), approved=a)
            except RuntimeError as e:
                print(f"[{i}/{len(jobs)}] skipped ({e}); run again to retry")
                continue
            ident = res["identified"]
            row = {"approved": a, "serving": s, "persona": p, "relation": relation(a, s), "status": res["status"],
                   "identified_key": ident["model_key"], "identified_version": ident["version"],
                   "identified_developer": ident["developer"], "fit_score": res["fit_score"],
                   "handoff": res["handoff_to_next_method"], "reasons": res["reasons"],
                   "version_right": ident["model_key"] == s,
                   "developer_right": ident["developer"] == DEVELOPER[MODELS[s][0]]}
            row["outcome"] = grade(row)
            rows.append(row)
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
            print(f"[{i}/{len(jobs)}] {a:17} <- {s:17} {p} | {row['status']:14} | {row['outcome']:18} | "
                  f"identified {ident['version']}")
            if args.judge_provider != "mock":
                time.sleep(args.delay)
    summary(rows)
    print(f"Saved -> {args.out}")


if __name__ == "__main__":
    main()