# Harness reference builder — Stage 2 prototype

**Implemented and registered:** `harness/v2` is a review-only, 17-model candidate. No model weights are fitted. The original v1 bundle and its checksums are unchanged. Stage 1 is deferred; it is not a dependency of this workflow.

## Why this is a reference refresh, not retraining

The teammate's Harness uses six fixed probes, empirical response profiles, examples, a judge LLM, and rule checks. The builder uses the same underlying method, with the following changes:

- Canonical model identities come from the model catalog and the approved training partition, rather than an eleven-model list. The original product-line distinction (e.g. Gemini Flash vs Gemini Pro) remains separate from the broad catalog family. Three catalog entries without a product-line field have explicit, documented mappings in `training/harness.py`.
- Only a verified `split-panel` for the six original `fingerprint_v0` probes is supported. Original query definitions are read from pinned v1; raw records lack prompt text, so the operator must confirm collection used those exact definitions.
- Reference answers come exclusively from training personas and sample indices 0/1. Sample 2, calibration, validation, and test responses are not used as references. Validation is checked for full panel and class coverage; no judge-based selection takes place.
- Keep blanks without recorded errors. Null/whitespace is normalized to empty text at runtime. Profiles include blank rates and use a separate blank mismatch rule; length is compared against nonblank reference responses. Existing rules otherwise retain their historical parameters; these are not newly calibrated thresholds.
- A versioned source snapshot contains only the runtime modules needed by the narrow identification API and the reference subset. No new copy of the card library, collector program, or legacy deployment database. Backend history and authoritative `cards/` remain separate. Legacy command-line collection and registration commands in the copied upstream source are not supported by v2.
- `review_only` prevents candidate acceptance, even when the legacy judge/rule output says identified. Legacy rule outputs are diagnostics only. This is not an open-set detector or a verified model swap.

## Real reference build

`collector_raw/agentic-2026-11-26`, split `rf_panel_v1`:

| Quantity | Count |
|---|---:|
| Models | 17 |
| Broad families | 6 |
| Fixed probes | 6 |
| Training personas | 4 (BK1, BK2, P01, P13) |
| Reference samples per model/probe | 8 |
| Reference records | 816 |
| Blank reference records | 28 |
| Training sample-2 records not used as references | 408 |
| Validation traces (BK3) | 51 |
| Reference coverage | 102/102 model/probe cells |

See `models/harness/v2/reference_report.json` for per-probe counts. The artifact pins the dataset and split hashes, v1 source hash, builder code hash, reference content hash, runtime dependency versions, and all required files. Raw snapshots remain immutable. The reference panel is a selected copy because the inference artifact must be usable without the training dataset; it is not a new unversioned raw collection.

## Commands (Windows Git Bash, repository root)

```bash
source .venv/Scripts/activate
python system/run.py training methods
python system/run.py config config/experiments/harness_v2.yaml
```

`harness/v2` is already registered, so the supplied build config is a reproduction record and will report `blocked_existing_version` if used unchanged. For a new approved fixed panel, copy `system/config/training/harness_candidate.json`, select the dataset/split and unused artifact version (e.g. `harness/v3`), and run:

```bash
python system/run.py training plan --config config/training/harness_refresh_local.json
python system/run.py training run --config config/training/harness_refresh_local.json --method harness --approve-dataset --register-candidates
```

If the effective reference payload, source snapshot, prompt definitions and judge settings match an existing file-ready v2-style candidate, the run reports `skipped_unchanged` and its reusable artifact IDs. No new version or automatic activation. A new dataset ID alone does not force a reference refresh. If the reference content changes, a new candidate is exported and optionally registered. The builder refuses missing/incomplete model-probe cells, overlapping train/validation personas, and unsupported split protocols. It never calls the judge during building.

The general orchestrator does not yet trigger on dataset registration/approval automatically; invoke the CLI explicitly. No Stage 1 training task will be scheduled (`blocked_stage1_deferred`).

## Replay and evaluate

Smoke test (no provider calls):

```bash
python system/tools/evaluate_harness_panel.py \
  --config system/config/experiments/harness_v2.yaml \
  --output local_harness_smoke.json --max-cases 3
```

Actual release smoke test: 3 validation traces, 0 runtime errors, 3 handoffs, 0 accepted IDs. The mock judge guesses randomly; accuracy is deliberately omitted. A broader 51-case attempt exceeded this environment's execution limit. All-blank input also passes the dedicated worker regression test.

For an explicitly authorized, billable judge experiment, configure the judge model/provider when building the candidate. This reuses the teammate's existing Google/OpenAI judge transport; no real API verification was performed here. Set its credential in the local environment (`GEMINI_API_KEY` for Google; `OPENAI_API_KEY` for OpenAI), never commit it or pass it in JSON. Confirm the model ID is actually supported by your provider account. Anthropic transport is not enabled for v2 because its inherited compatibility path is unvalidated. The judge receives reference examples and target response text; ensure you have permission to transfer these to that provider. Start with a limited validation run:

```bash
python system/tools/evaluate_harness_panel.py \
  --config system/config/experiments/harness_v2.yaml \
  --output local_harness_judge_validation.json \
  --partition validation --max-cases 3 --allow-live-judge
```

Use `--partition test` only for a frozen reviewed experiment. The case budget limits traces, not HTTP retry attempts or dollar spend. The inherited judge may retry and use substantial tokens; use a capped test account. Reports omit probe text and judge reasons. The method remains review-only and cannot update any reviewed baseline. No test set has been opened for this release's accuracy measurement.

## Remaining integration

- Run a controlled real judge smoke test, then validate on the reserved panel. The historical v1 rule thresholds and new blank rule are not calibrated for all 17 identities.
- Integrate the config-driven Stage 2 pipeline into the live HTTP worker, which still explicitly uses the v1 mock Harness path. No frontend contract or live production config is changed by this package.
- LoRA GPU execution and saved checkpoint evaluation remain pending. RF v2 is already trained, also review-only.
- Add new-model/catalog/card onboarding, then implement publication checks and eventual repository consolidation. Keep Stage 1 archived in place until explicit removal approval; production authentication and confidence threshold calibration remain deferred for this prototype.
