"""Compare two runs of probe_identify.py on the same chatbots, to show how consistent the judge is.

    python compare_runs.py results/results_probes4_baseline.jsonl results/results_probes5_baseline_run2.jsonl
"""
import json
import sys
from collections import Counter


def load(path):
    return {r["session"]: r for r in map(json.loads, open(path, encoding="utf-8"))}


def main():
    if len(sys.argv) != 3:
        exit(__doc__)
    a, b = load(sys.argv[1]), load(sys.argv[2])
    both = sorted(set(a) & set(b))
    if not both:
        exit("The two files have no chatbots in common.")
    n = len(both)
    for name, field in [("Developer", "pred_developer"), ("Family", "pred_family"), ("Version", "pred_version"),
                        ("Judge's own version", "judge_version")]:
        same = sum(a[s].get(field) == b[s].get(field) for s in both)
        print(f"{name:20} same answer in both runs: {same}/{n} ({100 * same // n}%)")
    for label, run in [("run 1", a), ("run 2", b)]:
        print(f"Version correct, {label}: {sum(run[s]['version_correct'] for s in both)}/{n}")
    both_ok = sum(a[s]["version_correct"] and b[s]["version_correct"] for s in both)
    print(f"Version correct in both runs: {both_ok}/{n}")

    changed = [s for s in both if a[s]["pred_version"] != b[s]["pred_version"]]
    print(f"\nChatbots whose final version changed between runs ({len(changed)}):")
    for s in changed:
        print(f"  {a[s]['true_model']:16} {a[s]['persona_id']:4} | run 1: {a[s]['pred_version']:16} | run 2: {b[s]['pred_version']}")
    print("\nBy model (version same in both runs):")
    by_model = Counter(a[s]["true_model"] for s in both)
    for m in sorted(by_model):
        same = sum(a[s]["pred_version"] == b[s]["pred_version"] for s in both if a[s]["true_model"] == m)
        print(f"  {m:16} {same}/{by_model[m]}")


if __name__ == "__main__":
    main()