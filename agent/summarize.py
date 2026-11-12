"""One summary of all automated test results, with 95% confidence intervals.

    python summarize.py results/rig_*.jsonl                        # identification runs (+ drift runs if given)
    python summarize.py results/rig_main_run1.jsonl --confusion    # also print the confusion matrix

For each identification results file (from probe_identify.py):
  - developer / family / version accuracy with a 95% Wilson confidence interval
  - flagged "Unknown" vs wrong without a flag
  - hidden model called "Unknown" (when a model was hidden)
  - handoff check: accuracy of the results the identifier KEPT (fit >= 0.7, version known) vs how many it
    handed off to the next method; a good identifier is right on what it keeps
  - by persona group and by model
Repeat runs (several files with the same hidden model) also get the range and how many chatbots agree in all.
Drift files (from test_drift.py) get caught / missed / false-alarm rates.

Writes the same text to results/summary.md so it can go straight into the write-up.
"""
import argparse, json, math
from collections import Counter, defaultdict
from pathlib import Path

from identify import HERE, MODELS

HANDOFF_BELOW = 0.7


def wilson(k, n, z=1.96):
    """95% confidence interval for k successes out of n (Wilson score)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.0f}%, CI {100 * lo:.0f}–{100 * hi:.0f}%)" if n else "–"


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def kept(r):
    return r.get("pred_version") not in (None, "Unknown") and (r.get("fit_score") or 0) >= HANDOFF_BELOW


def group(p):
    return "banking (BK)" if p.startswith("BK") else ("no persona (P13)" if p == "P13" else "other personas")


def identification(path, rows, lines, confusion):
    n = len(rows)
    hidden = rows[0].get("left_out")
    new = sorted({r["true_model"] for r in rows if r.get("unknown_model")})
    lines.append(f"\n## {Path(path).name}" + (f" (hidden: {MODELS[hidden][1]})" if hidden else "")
                 + (f" (models never seen: {', '.join(new)})" if new else ""))
    dev = sum(r["pred_developer"] == r["expected_developer"] for r in rows)
    fam = sum(r["family_correct"] for r in rows)
    ver = sum(r["version_correct"] for r in rows)
    unk = sum(r["pred_version"] == "Unknown" and not r["version_correct"] for r in rows)
    wrong = n - ver - unk
    lines += ["", "| Measure | Result |", "|---|---|",
              f"| Developer right | {pct(dev, n)} |", f"| Family right | {pct(fam, n)} |",
              f"| Version right | {pct(ver, n)} |", f"| Flagged \"Unknown\" (sent for review) | {unk} |",
              f"| Wrong without a flag | {pct(wrong, n)} |"]
    h = [r for r in rows if r["expected_version"] == "Unknown"]
    if h:
        lines.append(f"| Hidden or never-seen model called \"Unknown\" | {pct(sum(r['pred_version'] == 'Unknown' for r in h), len(h))} |")
    k = [r for r in rows if kept(r)]
    lines.append(f"| Kept by the identifier (fit ≥ {HANDOFF_BELOW}, version known) | {len(k)} of {n}; right: "
                 f"{pct(sum(r['version_correct'] for r in k), len(k))} |")
    handed = [r for r in rows if not kept(r)]
    lines.append(f"| Handed off to the next method | {len(handed)}; of these, right anyway: "
                 f"{sum(r['version_correct'] for r in handed)} |")
    lines += ["", "| Group | Version right |", "|---|---|"]
    by = defaultdict(list)
    for r in rows:
        by[group(r["persona_id"])].append(r["version_correct"])
    lines += [f"| {g} | {pct(sum(v), len(v))} |" for g, v in sorted(by.items())]
    by = defaultdict(list)
    for r in rows:
        by[r["true_model"]].append(r["version_correct"])
    lines += [f"| {m} | {sum(v)}/{len(v)} |" for m, v in sorted(by.items())]
    if confusion:
        names = sorted({r["true_model"] for r in rows})
        preds = names + sorted({r["pred_version"] for r in rows} - set(names))
        short = lambda s: s.replace("Gemini ", "Gem ").replace("Claude ", "Cl ").replace("GPT-5.6 ", "GPT ")
        lines += ["", "Confusion matrix (rows: real model, columns: final answer)", "",
                  "| Real \\ answer | " + " | ".join(short(p) for p in preds) + " |",
                  "|---|" + "---|" * len(preds)]
        c = Counter((r["true_model"], r["pred_version"]) for r in rows)
        for t in names:
            lines.append(f"| {short(t)} | " + " | ".join(str(c[(t, p)] or "·") for p in preds) + " |")
    return {"hidden": hidden, "n": n, "version": ver, "file": Path(path).name,
            "pred": {r["session"]: r["pred_version"] for r in rows}}


def drift(path, rows, lines):
    lines.append(f"\n## {Path(path).name} (drift test)")
    same = [r for r in rows if r["relation"] == "no swap"]
    swaps = [r for r in rows if r["relation"] != "no swap"]
    c = Counter(r["outcome"] for r in same)
    s = Counter(r["outcome"] for r in swaps)
    lines += ["", "| Measure | Result |", "|---|---|",
              f"| No swap: Verified | {pct(c['right'], len(same))} |",
              f"| No swap: Needs review (soft alarm) | {c['soft alarm']} |",
              f"| No swap: false alarm (Drift detected) | {pct(c['false alarm'], len(same))} |",
              f"| Swap caught (Drift detected) | {pct(s['caught'], len(swaps))} |",
              f"| Swap caught or sent for review | {pct(s['caught'] + s['flagged for review'], len(swaps))} |",
              f"| Swap missed (Verified) | {pct(s['missed'], len(swaps))} |",
              f"| Swapped-in model's version identified | {pct(sum(r['version_right'] for r in swaps), len(swaps))} |",
              f"| Swapped-in model's developer identified | {pct(sum(r['developer_right'] for r in swaps), len(swaps))} |"]
    lines += ["", "| Swap type | Checks | Caught | Review | Missed |", "|---|---|---|---|---|"]
    for rel in ("same line", "same developer", "other developer"):
        g = Counter(r["outcome"] for r in swaps if r["relation"] == rel)
        if sum(g.values()):
            lines.append(f"| {rel} | {sum(g.values())} | {g['caught']} | {g['flagged for review']} | {g['missed']} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--confusion", action="store_true", help="also print a confusion matrix per file")
    ap.add_argument("--out", default=str(HERE / "results" / "summary.md"))
    args = ap.parse_args()
    lines, runs = ["# Automated test summary", "",
                   "95% confidence intervals (Wilson). \"Kept\" = results the identifier did not hand off."], []
    for f in args.files:
        rows = load(f)
        if not rows:
            continue
        if "approved" in rows[0]:
            drift(f, rows, lines)
        else:
            runs.append(identification(f, rows, lines, args.confusion))
    groups = defaultdict(list)            # same hidden model and same chatbots = the same setup run again
    for r in runs:
        if "ablation" not in r["file"]:   # an ablation is the same answers re-scored, not a repeat run
            groups[(r["hidden"], frozenset(r["pred"]))].append(r)
    reps = {h: g for h, g in groups.items() if len(g) > 1}
    if reps:
        lines += ["", "## Repeat runs (same setup)", "", "| Hidden model | Runs | Version right (min–max) | Same answer in all runs |",
                  "|---|---|---|---|"]
        for h, g in reps.items():
            common = set.intersection(*(set(r["pred"]) for r in g))
            agree = sum(len({r["pred"][s] for r in g}) == 1 for s in common)
            accs = [100 * r["version"] / r["n"] for r in g]
            lines.append(f"| {MODELS[h[0]][1] if h[0] else 'none'} | {len(g)} ({', '.join(r['file'] for r in g)}) | "
                         f"{min(accs):.0f}–{max(accs):.0f}% | {agree}/{len(common)} |")
    text = "\n".join(lines) + "\n"
    print(text)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"Saved -> {args.out}")


if __name__ == "__main__":
    main()