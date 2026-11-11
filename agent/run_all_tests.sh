#!/usr/bin/env bash
# Runs every automated test of the agentic identifier and makes one summary.
#
#   bash run_all_tests.sh             # everything (~1,800 judge calls on Gemini 3.8 Flash, a few dollars)
#   FREE=1 bash run_all_tests.sh      # only the free parts: unit tests, card tests, ablation, summary
#   HELDOUT=P02,P07,P14 bash run_all_tests.sh   # also test on held-out personas (collect their data first)
#
# Run from agent/ with the collector's venv on and GEMINI_API_KEY in collector/.env.
# Every step can be stopped and restarted: finished results are skipped.
# Output: results/rig_*.jsonl, results/drift_test.jsonl, results/summary.md, results/cards_report.html

cd "$(dirname "$0")"
# Use the collector's venv if it exists (it has PyYAML), otherwise python3
if [ -x ../collector/.venv/bin/python ]; then PY=../collector/.venv/bin/python; else PY=python3; fi
R=results
MODELS="llama3.1-8b llama3.2-3b qwen3-8b qwen3.5-9b gemma3-4b gemini-3.8-flash gemini-3.1-pro claude-sonnet-5.5 claude-haiku-4.5 gpt-5.6-terra gpt-5.6-luna"
step() { echo; echo "=== $1"; }

step "1. Unit tests (free)"
$PY test_rules.py || echo "!! some unit tests failed (see above)"

if [ -z "$FREE" ]; then
  step "2. Repeatability: the main test 3 times with fresh judge calls"
  for i in 1 2 3; do
    $PY probe_identify.py --check baseline --out $R/rig_main_run$i.jsonl | tail -4
  done

  step "3. Hide every model, one at a time (11 runs)"
  for m in $MODELS; do
    $PY probe_identify.py --check baseline --leave-out $m --out $R/rig_hide_$m.jsonl | grep -E "Version accuracy|Hidden model"
  done

  step "4. Drift test: every approved model x every swap x BK1-BK4"
  $PY test_drift.py --out $R/drift_test.jsonl | tail -12

  if [ -n "$HELDOUT" ]; then
    step "5. Held-out personas: $HELDOUT"
    $PY probe_identify.py --check baseline --personas $HELDOUT --out $R/rig_heldout_main.jsonl | tail -4
    for m in claude-haiku-4.5 llama3.2-3b gemini-3.1-pro; do
      $PY probe_identify.py --check baseline --personas $HELDOUT --leave-out $m --out $R/rig_heldout_hide_$m.jsonl | grep -E "Version accuracy|Hidden model"
    done
  fi
fi

MAIN=$R/rig_main_run1.jsonl
[ -f "$MAIN" ] || MAIN=$R/results_probes6_all-models.jsonl     # free mode: use the latest saved run
step "6. Ablation on $MAIN (free, re-applies the checks with one turned off)"
for flag in no-sibling no-fallback no-selfname no-misfit no-daterule no-novelty; do
  rm -f $R/rig_ablation_$flag.jsonl
  $PY probe_identify.py --check baseline --rescore $MAIN --$flag --out $R/rig_ablation_$flag.jsonl | grep "Version accuracy" | sed "s/^/  --$flag: /"
done
rm -f $R/rig_ablation_judge-only.jsonl
$PY probe_identify.py --check baseline --rescore $MAIN --no-sibling --no-fallback --no-selfname --no-misfit --no-daterule --no-novelty \
  --out $R/rig_ablation_judge-only.jsonl | grep "Version accuracy" | sed "s/^/  judge only: /"

step "7. Domain cards on every run (free)"
$PY test_cards.py $(ls $R/rig_main_run*.jsonl $R/rig_hide_*.jsonl $R/rig_heldout_*.jsonl 2>/dev/null || echo $MAIN) | grep -E "Lookup|right card|FAIL"
$PY ../cards/check_cards.py | tail -3

step "8. Summary with confidence intervals (free)"
$PY summarize.py $(ls $R/rig_*.jsonl $R/drift_test.jsonl 2>/dev/null) --out $R/summary.md > /dev/null
echo "Summary -> $R/summary.md   Cards report -> $R/cards_report.html"