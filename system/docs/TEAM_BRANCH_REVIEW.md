> **Follow-up:** The extracted v2 LoRA notebook now has an orchestrated trainer; see [LORA_TRAINING.md](LORA_TRAINING.md). No new real checkpoint produced.

# Teammate repository intake — November 26, 2026

Compared the three uploaded ZIPs to the latest training-orchestrator system.
Ignored `.git/`, `.venv/`, caches, teammate `system/` snapshots, local deployment
records, generated results, and duplicate collector code. No teammate Python
or notebook cells were executed. No previous artifact or raw version removed.

## LoRA

Extracted code/Markdown sources from the three notebooks into
`research/team_sources/lora/`; stripped saved outputs, attachments and runtime
metadata. `SOURCE_MANIFEST.json` records original and extracted hashes. These
are research source handoffs, **not executable training strategies yet**.

| Source notebook | Actual code configuration | Saved notebook results (not independently rerun) | Recommendation |
|---|---|---|---|
| `lora_llm_identification(open_models).ipynb` | Qwen2.5-0.5B, rank 16, alpha 32, dropout .05, 384 tokens, 4 epochs, LR 2e-4, 5 open-model labels | 0.673 exact, .897 family, 697 test rows | Closest recipe to our existing 0.5B artifact; do not assert checkpoint provenance from notebook alone |
| `lora_llm_identification(closed_models).ipynb` | Same 0.5B recipe, two Gemini classes, 384 tokens, 4 epochs | .661 exact on 540 test rows, .674 TF-IDF baseline | Separate experiment, not all closed models |
| `v2_lora_finetuning.ipynb` | Qwen2.5-1.5B, rank 32, alpha 64, dropout .05, 512 tokens, 8 epochs, LR 1e-4, weight decay .01, 5 labels | .676 exact, .894 family, 697 test rows | Best source for a generalized future trainer; still five-class recipe |

The v2 notebook's README is broadly consistent with the 1.5B recipe, not the
0.5B notebooks. All three notebooks derive labels with sorted model keys and
split by prompt ID. They filter blanks and cap training rows per class. The
open-model order printed by the notebooks is gemma3-4b, llama3.1-8b,
llama3.2-3b, qwen3-8b, qwen3.5-9b. This is **not checkpoint-specific proof** for
our already integrated LoRA v2. The notebook ZIP contains no exported PEFT
adapter weights, adapter configuration, or exact base revision; no replacement
LoRA artifact was created. The team needs to provide a pinned commit and export
weights, tokenizer/input contract, actual label map, head shape, dependency
versions and training-run metadata. For automated retraining, convert the
notebook to a non-Colab strategy using orchestrator train/validation exports;
represent blanks consistently in both inference and fitting, use all intended
labels and avoid mixing prompt-set coverage artifacts. Train/evaluate on GPU
with a reproducible environment. Retain `review_only` until validation.

## Agentic / Harness

The uploaded branch's `agent/identify.py`, `probe_identify.py`, `identify_api.py`,
`check_chatbot.py`, `card_lookup.py` and `test_rules.py` are byte-identical to
`models/harness/v1/agent/`. All 53 files under branch `cards/` match the pinned
artifact's cards, including `cardlib.py`. Collector model/licence/persona and
fingerprinting prompt YAMLs also match. No duplicate runtime code required.

- Reuse `identify_api.get_probes()` and `identify(answers, domain, ...)` through
  the existing Harness adapter, not through a second inference pipeline.
- `identify.py` contains 11 known exact-model IDs; the new 17-model raw data
  does not expand that lookup automatically. The other six may be used for
  experiments on unseen versions, not silently added to the known set.
- `check_chatbot.py` handles references, fit, handoff and legacy deployment
  baselines. `probe_identify.py` implements scoring/misfit/sibling/unknown rules
  and test sampling. The reference sample indices are 0 and 1; test sample 2.
  The existing Harness artifact pins only its reference rows. The runtime
  currently drops empty strings; review this deliberately before updating it.
- `probe_prompts.yaml` is a six-probe subset of the full prompt bank; parsed
  text matches exactly. Used the actual six IDs as the RF candidate pool.
- `agent/test_cards.py`, `test_drift.py`, `compare_runs.py`, `summarize.py`,
  `run_all_tests.sh`, `README.md`, `WRITEUP.md` and results summaries are useful
  evaluation/documentation sources. Do not run the shell script blindly: it
  can invoke a paid judge. Do not import demo deployments or generated results
  into backend history. No need to duplicate these files into runtime now.
- Harness uses reference/profile construction and an external judge, not
  fitted RF/LoRA weights. Updating the known list or reference data still
  requires a new version and validation (including family/developer mapping,
  card availability, holdout exclusions and real judge). The colleague's
  write-up reports 23/24 unknown-version cases and 67/83 exact known cases;
  those are historical colleague-reported results, not independently verified
  or evidence about an unseen seventh family. Our prototype worker still uses
  the mock judge. The existing backend's canonical broad families differ from
  Harness product lines (e.g. GPT Terra/Luna); reconcile mappings before
  publishing new references.

## Random Forest

`prepare_fingerprint_rf.py` and `train_fingerprint_rf.py` are byte-identical
with `reference_random_forest/` versions. The alternate hyphenated preparation
script is an earlier/different implementation, not a new fitted checkpoint.
Existing trainer consumes derived CSVs, fits per-response forests and outputs
metrics; no newly exported RF checkpoint present. Reuse original 14 text
feature calculations, not its original 52-column prompt/backend-metadata ABI.
See `RF_MULTI_PROMPT.md` for the new automated fixed-probe trainer, adapter and
actual held-out experiment. Keep v1 and v2 side-by-side (v2 review-only).

## Data intake

Registered exact 21 raw JSONL files of Agentic as
`datasets/collector_raw/agentic-2026-11-26/`: 9,176 records, 17 models. 8,888
record IDs overlap the previous 9,717-record version, 288 are new to it. Do not
combine these snapshots without record-level deduplication. The previous
snapshot has no common prompt across all 17 models because Gemini Pro lacks
the fingerprint probe responses. Agentic provides all six probes for every
model, persona and sample, plus eight failed attempts with successful retries.
The new snapshot is retained as the active source of RF v2 (not historical
processed CSVs). Nothing in prior dataset or active artifact directories was
removed. Raw data is pending privacy/licence review before distribution.
