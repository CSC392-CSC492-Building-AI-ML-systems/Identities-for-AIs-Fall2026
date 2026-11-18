> **November 18, 2026 update:** LoRA `lora/v2` weights are installed and selected in production YAML. The registry reports its files present and checksummed. This does **not** mean real LoRA inference has been verified: the class-label mapping is provisional, the base revision is temporarily `main`, and unknown-model rejection remains `review_only`. Old lines below describing missing `lora/v1` weights refer to the historical configuration. Read the current [`README.md`](../README.md) and [`TBD.md`](../TBD.md) for authoritative release status. Harness live judge and shared probe replays remain unvalidated.

# Unified evaluation — researcher and developer guide

## Architecture

- `FingerprintPipeline`: the unchanged production orchestrator; never receives evaluation ground truth.
- `Stage1Strategy` and `Stage2Identifier` / `Stage2Strategy`: interchangeable inference implementations selected by the Factory.
- `EvaluationRunner`: existing per-case scoring logic, still useful for direct research scripts.
- **New:** `fingerprinting/eval_cases.py` loads normalized cases and explicitly separates expected identity from the true identity.
- **New:** `fingerprinting/eval_suite.py` builds the selected real strategies, runs independent and E2E evaluations, tracks missing artifacts, and writes unified reports.
- **New:** `fingerprinting/eval_cli.py` provides a single command-line entry point.

The published `models/*/v*/manifest.json` files are **immutable** and checksummed. New classifier versions are selected using YAML, with no edits to the evaluator or orchestrator. All reports record selection/configuration hashes and per-artifact manifest digests.

## Installation and quick start (from the GitHub repository root)

```bash
python -m pip install -r system/requirements-integrated.txt
python system/run.py test

# One offline run: Stage 1, each Stage 2 method independently, configured E2E.
# LoRA is marked missing; full E2E is BLOCKED, not silently truncated.
python system/run.py evaluate --rf-pilot --scope all --limit-per-model 4 \
  --output reports/unified_pilot

# Stage 1: all three classifier approaches on the same pilot records
python system/run.py evaluate --rf-pilot --scope stage1 \
  --all-stage1-approaches --output reports/stage1_compare

# Stage 2 RF independently (uses real trained forest, review-only acceptance)
python system/run.py evaluate --rf-pilot --scope stage2 \
  --methods random_forest --output reports/rf_only

# Stage 1 + RF SUBSET, excluding LoRA and Harness intentionally
python system/run.py evaluate --rf-pilot --scope e2e \
  --methods random_forest --output reports/e2e_rf_subset

# Harness six-probe replay, mock judge: measures only plumbing and rules
python system/run.py evaluate \
  --cases testdata/evaluation/harness_bk1_replay_cases.jsonl \
  --scope stage2 --methods harness --judge-provider mock \
  --output reports/harness_mock_diagnostic
```

Real Harness judge calls require **both** `--judge-provider google` (or another configured provider) and explicit `--allow-live-judge`; credentials must be supplied through the runtime environment, not committed. The judge may send stored answers to an external API and incur costs. This CLI is offline with respect to the target model; it is NOT an automated live target-probing evaluation runner. A registered live target will need an injected `TargetClient` and an approved dataset collection protocol.

You can evaluate the originally configured fallback with `--scope e2e`, but the runner refuses to construct it while LoRA weights are missing. `--allow-partial-e2e` will run only the ready methods and **mark the result as partial**, never as the complete production pipeline. Alternatively `--methods random_forest` requests an explicit subset, also marked partial.

## Case format (JSON Lines, one scenario per line)

```json
{"case_id":"example-001","dataset_id":"independent_eval_v1","split_id":"heldout_prompts","actual_model_id":"llama3.2-3b","expected_model_id":"llama3.1-8b","persona_id":"BK1","prompt_group_id":"group_01","source_record_ids":["source-129"],"initial":{"prompt_id":"Q01","prompt_text":"Explain recursion.","response_text":"An example response.","output_tokens":4,"latency_ms":90},"replay_probes":{}}
```

`expected_family_id` and `actual_family_id` are optional for cataloged models and are validated against the canonical catalog when provided. A truly out-of-catalog `actual_model_id` is allowed for open-set negative evaluation **only when an explicit `actual_family_id` is included**. Expected identities must exist in the catalog so Stage 1 can validate the declared deployment.

To use Harness offline, add all six responses under `replay_probes` with keys `LM-01`, `LM-05`, `LM-06`, `I1`, `I2`, `V1-15`. Each entry must have its original `prompt_text`, `response_text`, and matching `prompt_id`. These responses must come from the same chatbot/deployment/persona observation; never mix records from unrelated sessions. The adapter checks probe text against the versioned Harness artifact, and missing probes produce explicit errors rather than synthetic answers.

`--rf-pilot` converts bundled `testdata/random_forest/heldout_raw_cases.jsonl` into multiple expected/actual scenarios. It uses the **original response-held-out, fixed-prompt P13 split**, randomly picks up to `--limit-per-model N` responses for each model (seed 42), and makes a same-identity case when Stage 1 supports it plus a simulated swapped-deployment case. It does not use a novel prompt split. Each reused response retains the same `source_record_ids`; metrics across such pairs are correlated. The original data contains some prompt-injection-style questions by design; these are test **data** for the detector, not instructions.

## Reports and fields

Each command creates:

- `summary.md`: human-readable metrics, blocked items, interpretation warnings.
- `summary.json`: dataset statistics, input digest, configuration selection hash, artifact-readiness states, result-file index.
- `stage1_<approach>.json`, `stage2_<method>.json`, `e2e.json`: detailed per-case predictions and per-scope metrics with artifact/version provenance. Only completed scopes get a file.
- `metrics.csv`: scalar metric table, one scope/metric per row.
- `case_results.csv`: compact result rows without raw prompt/response text; includes routing and attempt data for debugging.

The report distinguishes **candidate top-1 accuracy** from **accepted identification accuracy** and **final pipeline accuracy**. LoRA and RF default to `review_only`: their candidate rankings are evaluable, but they do not confirm identity or drift. The harness `mock` provider has no valid identification-accuracy measurement; reported accuracy fields are suppressed. When the RF pilot lacks six-probe replays, Harness is flagged as `incomplete_missing_probe_data`.

Independent Stage 2 evaluation runs **regardless of Stage 1's routing decision**. E2E evaluation obeys Stage 1's early-accept logic and the selected fallback order, so it can measure false verifications that hide real model changes. A `run_all` strategy invokes every method and selects the first accepted output, providing separate evidence from production fallback.

Metrics include Stage 1 decision coverage/accuracy and false verification, Stage 2 per-method attempted/candidate/acceptance counts, and E2E exact model accuracy, review rate, false drift alarms, missed drift, stage2 invocation and routing. Some rates are conditional and have `null` when their denominator is zero. For future statistical reporting, `confidence_interval()` implements a Wilson interval helper, **but** the unified runner does not auto-apply binomial CIs to correlated swap pairs. Use a true independent sample or cluster-aware confidence interval procedure for publishable uncertainty estimates.

## Scientific comparison limitations

1. The available classifiers use different training splits and supported model sets. The bundled P13 RF pilot cannot support a fair head-to-head claim without additional leakage review.
2. `stage1_lr/v1` covers four Gemini/Llama identities, `lora/v1` and `random_forest/v1` cover five open-weight identities, and `harness/v1` covers eleven. Include unsupported-identity negatives when calibrating open-set behaviour.
3. Historical RF accuracy of ~93% depends on fixed prompts and environment-specific features. It is not generalization to unseen deployment prompts.
4. Stage 1 LR saved in scikit-learn 1.6.1 and RF reconstructed in 1.8.0; their combined test passing does not guarantee long-term pickle compatibility. Use pinned environments or safe isolation.
5. Full production LoRA → Harness → RF cannot be evaluated until the LoRA adapter weights, valid acceptance rules and a genuine Harness judge are available. Every remaining task is in **[system/TBD.md](../TBD.md)**.

## Repo integration

The archive contains **one top-level folder, `system/`**. Extract that folder into the root of the existing GitHub repository. All code, manifests, models, configs, tests, docs, reports, and `TBD.md` remain inside `system/`, avoiding conflicts with existing root-level files. From the repo root, use `python system/run.py ...` or `./system/run.sh ...`; the launcher runs the subsystem with `system/` as its working directory. Training scripts from other teams can remain in their own root-level folders and import the versioned inference adapters as needed.

## November 2026 update: Stage 1 is opt-in for E2E

- The default pipeline configuration has `stage1.enabled: false`; E2E evaluations start directly at Stage 2. Independent `--scope stage1` testing is still supported.
- To compare with Stage 1 enabled, run `python system/run.py evaluate --rf-pilot --scope e2e --methods random_forest --use-stage1` from the GitHub root. Omit the switch to evaluate Stage 2-only routing, or use `--no-stage1` to override a configuration that enables it.
- `stage1.verdict: skipped` and `stage1_enabled: false` explicitly record that verification was bypassed. Final `identified` is possible when no expected model is provided; such cases do not contribute to drift denominators.
- Legacy `config/*.yaml` without `stage1.enabled` load with Stage 1 off. `config/stage1/*.yaml` explicitly enables Stage 1.
- The full three-method production chain is still blocked by the missing LoRA weights; a `--methods random_forest` run is a **subset** and uses the RF `review_only` policy.
