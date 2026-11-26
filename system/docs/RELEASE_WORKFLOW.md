# Automated evaluation and reviewed publication (Stage 2 prototype)

The existing dataset onboarding, training orchestrator, registry, Pipeline Factory and EvaluationRunner remain authoritative. `release` connects them; it does not create another artifact registry or an identity acceptance policy. Stage 1 is deferred. The commands use trusted local artifacts (including executable Python and joblib); they are not a service for untrusted uploads. No production configuration is changed by this workflow.

## Evaluate existing RF artifacts (CPU only)

Run in PowerShell from the repository root after installing `system/requirements-integrated.txt` in your environment. All paths passed to `system/run.py` are relative to `system/`, unless absolute.

```powershell
python system/run.py release evaluate --candidate random_forest/v2 --baseline random_forest/v1 --trust-artifacts --output .local/rf_review_validation.json
```

The candidate's dataset and split manifests must match its provenance. The runner uses the complete validation partition by default and replays the same case IDs through the real Factory for both versions. No target calls are made. Validation is for review/selection, not independent testing; `--partition test` is available for a separately frozen evaluation. Do not repeatedly select or tune against test results. The candidate and baseline must be versions of the same adapter. Current comparison protocol is fixed-panel only. The legacy RF receives one predeclared initial probe (`I1` by default), no output-token or latency metadata; panel methods receive their own required probes, whose texts must match the collection definitions. `--prompts` accepts the actual collection YAML when using a new pool, and `--initial-probe` selects a predeclared initial probe. Raw collector records lack the original prompt text; operators must verify that definitions are the ones actually used. Do not choose the initial probe after examining test performance.

The reports include the whole cohort, shared-label cohort (old vs new on exactly the same case IDs), per-class counts, exact candidate accuracy, family accuracy, macro-F1, missing predictions, errors, candidate coverage, confusion matrix, paired wins/losses, replay query count and measured identifier runtime. Missing predictions count as incorrect. Confusion axes include an explicit no-prediction label. LoRA evaluates individual responses; RF and Harness evaluate reconstructed panel traces. These units are not interchangeable. Score calibration and unknown-family recognition are not evaluated. Reports do not contain raw prompt/response text or judge reasons.

Actual shipped example: `reports/rf_release_comparison_validation.json` (51 traces, 17 identities; RF v2 49/51, v1 3/51; common five identities v2 15/15, v1 3/15). Different evidence budgets and legacy input mismatch mean these are illustrative comparisons, not a controlled algorithm-only improvement. The validation persona was used for RF v2 prompt selection, historical overlap has not been excluded, and v1 did not support 12 of the 17 labels. Use this report as an example only; re-run on your own environment before publication. Source, catalog and dependency fingerprints must match. Local report metadata is not cryptographic attestation of model execution; trusted reviewer and source control remain necessary.

## Automatic evaluation after training

Use a fresh artifact version in the training configuration. To train RF and immediately evaluate its registered output:

```powershell
python system/run.py training run --config config/training/NEW_RF_CONFIG.json --method random_forest --approve-dataset --register-candidates --evaluate-candidates
```

The default comparison baseline is the selected method version in `config/experiments/live_stage2_review.yaml`. Override with `--evaluation-base-config` when using a published profile. RF uses the prompt definitions recorded in its training config; for other collections use `--evaluation-prompts`. The training result is retained independently; an evaluation block does not erase the registered candidate. If a training run is already complete:

```powershell
python system/run.py release evaluate-run --run-id YOUR_TRAINING_RUN_ID --trust-artifacts
```

The automatic evaluator only uses validation, skips unregistered/unchanged outputs and Stage 1, and never makes external judge calls. It saves `release_evaluation/summary.json` and individual reports inside the training run directory. A blocked evaluation returns a nonzero CLI status; no candidate is automatically activated. If the baseline LoRA checkpoint is unconfirmed, scoring it is refused; evaluate the first valid LoRA candidate without a baseline if there is no valid selected predecessor. A general unseen-prompt release comparator is not yet supported; use the existing standalone LoRA evaluator for that protocol. There is no event scheduler: dataset approval still explicitly triggers training.

## Harness and LoRA

Harness mock smoke (no accuracy claim; defaults to three cases if no explicit limit):

```powershell
python system/run.py release evaluate --candidate harness/v2 --baseline harness/v1 --trust-artifacts --max-cases 3 --output .local/harness_smoke.json
```

For actual judge evaluation, configure the judge dependencies and credential locally; review provider costs/data transfer. Use `--allow-live-judge --max-cases 51` for a complete 51-trace validation cohort, if authorized. Both compared versions must use the same judge provider/model. Mock and partial reports cannot authorize publication. No live judge call has been tested in this milestone. Actual LoRA comparison requires a trained checkpoint, confirmed label mapping, pinned base revision and inference dependencies; the shipped v2 mapping is unconfirmed, so it cannot be scored. When a new LoRA v3 is validated, `release evaluate --candidate lora/v3 --trust-artifacts --output .local/lora_v3_review.json` is the first-release route. Real LoRA execution remains untested. No NVIDIA GPU is needed for RF.

## Reviewed publication and rollback

Publication creates a *new immutable-by-convention review profile*, not a deployed/confirmed classifier or a GitHub release. Explicit operator review is required. No automatic identity acceptance or baseline updates are enabled. Example comparing the old RF-only profile with the new candidate:

```powershell
python system/run.py release publish --evidence .local/rf_review_validation.json --base-config config/experiments/random_forest_only.yaml --release-id rf-v2-review --review-note "Reviewed fixed-panel validation, limitations and class coverage; prototype only." --acknowledge-exploratory
```

Use `--base-config config/experiments/live_stage2_review.yaml` instead to preserve the two-method demo profile (it already selects RF v2). In future the base should be the actual currently chosen review profile. The tool verifies exact current artifact files and manifest digests, source/catalog/dependencies, dataset/split hashes, complete reconstructed cohort, candidate label coverage and recomputed metrics. Missing/error/accepted candidate predictions block publication. A selected predecessor must match the compared version (unless the selected artifact is already the candidate); dropping supported identities is blocked. A decline in any shared-label metric requires an explicit `--acknowledge-regression`. This is a review gate, not a scientifically chosen performance or confidence threshold. No mock or partial evidence can publish. All selected artifacts must satisfy the existing Stage 2 review-only profile restrictions, including compatible prompt definitions and the six-additional-probe prototype budget.

Result: `system/.local/releases/rf-v2-review/{pipeline.yaml,receipt.json,evaluation.json}`. Other versions, source data and production/default profile remain unchanged. To actually select the published profile for the localhost worker, stop/restart the worker using the normal local dev auth/crypto setup in `BACKEND_STAGE2_REVIEW.md` and the explicit config argument:

```powershell
python -m system.backend.worker --kind stage2 --loop --pipeline-config system/.local/releases/rf-v2-review/pipeline.yaml
```

This may make billable target calls only when processing authorized live jobs; optional live judge remains separately consented. For rollback:

```powershell
python system/run.py release rollback --source-release rf-v2-review --release-id rf-v1-restored --review-note "Restore the previously selected review profile for comparison."
python system/run.py release history
```

Rollback verifies prior artifacts and saved profile/evidence hashes, then creates a new profile containing the previous selection. Restart the worker with the restored profile to actually change runtime selection. No in-place config updates or deleted model versions. Local release history is excluded from Git by `.local/`; retain approved receipts/reports under your team's reviewed version control or archive procedure if desired. Checksums catch accidental tampering; local files are not signed, crash-proof transactions or an approval/authentication service.

## Validation

122 focused tests passed, including 12 new release tests, actual RF v1/v2 paired replay, temporary RF training-to-automatic-evaluation, publish/rollback in a temporary copy, and core registry, Factory, evaluator, training and layout regressions. No actual judge call, real LoRA training/evaluation or full legacy suite. Existing artifact bytes, catalog, raw datasets, default configurations and backend code preserved. Stage 1, confidence thresholds, independent holdout certification, automated deployment, production auth and unknown-family detection remain deferred. No additional cleanup performed.
