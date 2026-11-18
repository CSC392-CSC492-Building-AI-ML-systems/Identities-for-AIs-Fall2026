# TBD — Integration gaps, manual prerequisites, and evaluation risks

> **Location:** `system/TBD.md` relative to the GitHub repository root.
> Use `python system/run.py ...` from the repository root, or `cd system` before
> running the older `python -m fingerprinting...` commands referenced below.

This file tracks **unresolved work**. A passing integration test does not mean the entire pipeline is deployment-ready, nor that a classifier correctly identifies unfamiliar models. Update the checkboxes, owner, evidence, and version when each item is resolved. **Do not put API keys or private model data in Git.**

## P0 — Required to run the configured LoRA → Harness → Random Forest pipeline

- [ ] **Obtain the actual LoRA adapter bundle.** Ask the LoRA teammate for `my_lora_adapter.zip` containing `adapter_model.safetensors` and `adapter_config.json`, *including the trained sequence-classification head*. Install under `models/lora/v1/` with `python tools/install_lora_adapter.py my_lora_adapter.zip --base-revision <40-char-HF-commit>`. Confirm tokenizer/base-model revision, artifact checksum, CPU/GPU requirements, class label order, and notebook output parity. **Owner:** LoRA teammate. **Evidence:** `python -m fingerprinting.config_cli config/production.yaml --root . --require-ready` and a real checkpoint parity report.
- [ ] **Evaluate the Harness with a genuine judge provider.** Mock provider validates plumbing only and never counts as real identification accuracy. Supply credentials through environment, not tracked files. Use explicit `--judge-provider google --allow-live-judge` only on approved datasets, record API model/version, probe budget, repeatability, latency and cost. **Owner:** Harness teammate/integration team.
- [ ] **Collect complete, paired Harness probe replays for the common test cohort.** Six probes must be gathered from the *same actual target model + persona/deployment + evaluation session*, not mixed with responses from other sessions. Missing probes must be reported; no fabricated answers. Set aside an independent holdout disjoint from Harness reference data.
- [ ] **Define and validate LoRA unknown-model rejection.** Current classifier always ranks its five known classes; `review_only` prevents false acceptance but also prevents LoRA from confirming a model. Tune and freeze an acceptance policy on held-out known and unknown models (report false acceptance, coverage, precision, per-class performance) then publish a new immutable artifact/version with supporting `validation_id`. Do not select a threshold based on final test results.
- [ ] **Define and validate Random Forest unknown-model rejection.** Same closed-set limitation; `random_forest/v1` deliberately returns candidates only (`review_only`). Evaluate appropriate out-of-set and same-family near-neighbour negatives, and create a new approved version/policy. `review_only` is NOT a discovered identity.
- [ ] **Confirm operational rules for ambiguous cases.** Decide required coverage/precision, how `Unknown` maps to `needs_review`, whether a fallback method may override another accepted method (currently first accepted wins), and whether the platform should offer a human-review workflow. Include policy version in evaluation metadata.

## P1 — Scientific validity and reproducibility

- [ ] **Create one frozen multi-method evaluation dataset.** Existing Stage 1, LoRA, Harness and RF historical evaluation splits are not aligned. Design prompt-group, persona, model-family, and time/environment splits; disclose overlap with any reference, fine-tuning, RF or threshold-calibration data. Ground truth must not enter inference context.
- [ ] **Replace the bundled RF pilot for final claims.** `testdata/random_forest/heldout_raw_cases.jsonl` uses fixed prompts and previously observed backend conditions. Multiple simulated approved/serving pairs reuse one response. These are *correlated* scenarios; raw case-level Wilson intervals would overstate evidence. Use deployment-level or prompt-group resampling for final confidence intervals.
- [ ] **Test model-swap false verification explicitly.** Stage 1 may verify a changed model, preventing all Stage 2 methods from running. Report false verification, false alarms, review rate, and drift detection recall, broken down by within-family vs cross-family swaps, including out-of-catalog models.
- [ ] **Make Stage 1 behaviour for unsupported expected models explicit.** `stage1_lr/v1` covers two Gemini and two Llama models only. Decide whether unsupported expected IDs should immediately skip to Stage 2, raise a typed unsupported result, or use a separate verification strategy; currently the Stage 1 adapter raises and the pipeline records an error before Stage 2.
- [ ] **Improve model-ID candidate calibration.** A maximum softmax probability or RF vote fraction is *not* a calibrated correctness probability. Compare ROC/PR and selective risk vs coverage on known/unknown holdouts, including rare classes.
- [ ] **Confirm and freeze compatible Python/scikit-learn environments.** Stage 1 `.joblib` files were trained under scikit-learn 1.6.1; reconstructed RF artifact uses 1.8.0. Cross-version pickle compatibility is not guaranteed. Isolate processes/environments or retrain/re-export in a supported common version, then retest parity. Load only trusted checksummed artifacts.
- [ ] **RF robustness to prompts and serving metadata.** `random_forest/v1` uses prompt-ID features, output token count and latency. Evaluate without those signals and under novel prompt IDs, other APIs/hardware and missing measurements. Preserve the exact 52-feature ABI for this version; retrained variants need a new version and possibly a new adapter.
- [ ] **LoRA parity and shift evaluation.** Repeat notebook inference on raw recorded responses and test across prompt, persona, model and system-prompt shifts. The saved notebook's reported 67.6% comes from a different evaluation protocol than RF's 93% and is not directly comparable.
- [ ] **Verify model registry and domain-card semantics.** Stage 1 groups Gemini Pro/Flash under broad `gemini`; Harness has distinct product lines. Map exact model keys centrally, derive family/developer from registry, avoid Stage 2 family classification as a required outcome.
- [ ] **Harmonize evaluation reporting across cohorts.** The unified suite tracks `dataset_id`, `split_id`, persona and source record identity; it does not yet provide grouped statistical uncertainty or paired-significance tests. Reports are exploratory until a joint frozen test protocol exists.

## P2 — Operational and future work

- [ ] **Run the full configured pipeline on a controlled live deployment.** Connect a live `TargetClient`, set API quotas, timeouts/retries, rate limits, judge cost controls and record exact responses, versions and timestamps. Do not treat mock results as live evidence.
- [ ] **Add resource/cost benchmarks.** Measure cold/warm LoRA load time, GPU VRAM, Harness six-probe + judge cost, RF feature-extraction latency, failed calls and fallback frequency.
- [ ] **Add CI workflows** for synthetic contract tests, artifact readiness and optional offline integration tests. Avoid API calls and heavy Hugging Face downloads on ordinary pull requests. Exclude model secrets/credentials from logs.
- [ ] **Implement model/dataset onboarding (separate project task).** Add validated registry publication, updated cards, dataset provenance, retraining workflows, and immutable artifact promotion. This is intentionally *not* implemented by the unified evaluator.
- [ ] **Agree on artifact storage in Git.** Trained `.joblib` files and reference data are currently bundled; consider Git LFS or artifact releases if repository size grows. Do not blindly commit full user conversation datasets, tokens or credentials.

## Current shipped capabilities and honest scope

- Stage 1 Logistic Regression: trained models integrated and parity-tested, but only four known target identities.
- Stage 2 LoRA: adapter integrated but trained weights missing; the full configured pipeline is **blocked** by default.
- Stage 2 Harness: six probes and offline reference bundle available; `mock` judge **does not measure real accuracy**.
- Stage 2 Random Forest: saved refit five-class classifier is ready; uncalibrated acceptance means candidate-only results.
- `python -m fingerprinting.eval_cli --rf-pilot --scope all` performs real independent Stage 1 and RF evaluation and diagnostic Harness testing, and records the blocked full E2E pipeline.
- `python -m fingerprinting.eval_cli --rf-pilot --scope e2e --methods random_forest` evaluates an **explicit Stage 1 → RF subset**. This is not the full LoRA → Harness → RF pipeline, and its current `review_only` policy produces review outcomes.

Each resolved item should include **owner, date, artifact ID, dataset version, and validation report** before checking it off.

## UI / backend handoff (November 2026; Stage 1 opt-in update)

- [ ] **Implement a real HTTP/async job API.** `docs/UI_INTEGRATION.md` proposes routes and payloads, but this repository currently contains Python functions and CLI commands, not an HTTP server. Backend owner must implement, authorize and test the routes.
- [ ] **Implement authorized live target connections.** A production `TargetClient.ask()` must query a registered deployment for the Harness's six probes; browser-supplied arbitrary URLs or secrets must not be used.
- [ ] **Publish capabilities and status mapping to UI.** Expose Stage 1 toggle (default OFF), method readiness, supported model IDs, domain-card availability and per-method limitations. Distinguish accepted identities from review-only candidates.
- [ ] **Confirm product semantics for Stage 2-only comparison.** With an expected identity, an accepted Stage 2 result may be `verified`/`drift_detected`; without one it returns `identified`. Agree on whether and how to label this in user-facing monitoring alerts; an accepted prediction is not independently proven ground truth.
- [ ] **Run production-style UI/backend integration tests.** Include Stage 1 off/on, missing expected IDs, long Harness jobs, timeout/cancellation, unavailable LoRA checkpoint, missing probes, error mapping and sensitive-data redaction.
