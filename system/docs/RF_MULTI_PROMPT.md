# Multi-prompt Random Forest — experimental v2

Implemented an RF adaptation of Pasquini, Kornaropoulos and Ateniese,
*LLMmap: Fingerprinting for Large Language Models*, USENIX Security 2025,
sections 3.1, 5, 6.2, 7.1 and Appendix C / Algorithm C.1 (printed pp.
302, 305–307, 315). The paper uses embedding vectors and self-attention over
query-response traces. Our method uses the same fixed multi-query and greedy
selection ideas, **not the same network**. No paper accuracy claim transfers.

## Method

- Six eligible query IDs: LM-01, LM-05, LM-06, I1, I2, V1-15. Exact prompt
  text comes from Agentic collector `probe_prompts.yaml`, matching pinned
  `fingerprinting_prompts.yaml`. Only six common probes exist across 17 models;
  broader prompt selection needs more balanced collection.
- Reconstruct each trace by canonical model, persona, sample index, prompt-set
  version and matching recorded sampling configuration. No explicit session
  IDs: these are grouped independent stateless library calls, not verified
  conversational traces. Do not mix deployments or make up missing answers.
- Split **by persona**, not by prompt, because selected probes must be repeated
  at inference. Train BK1/BK2/P01/P13 (204 traces); calibration P12 (51, unused);
  validation BK3 (51); test BK4/P15 (102). Each model has three samples per
  persona, 24 traces total (408 across 17). 2,448 valid records, eight failed
  retries excluded, other non-panel records left in raw snapshot. Sample indices
  are consistent but sampling parameters can differ between providers. Four
  train personas and one validation persona are limited evidence. Not an unseen-
  prompt benchmark, not an independent end-to-end pipeline test.
- Each response uses 14 original text statistics, one blank flag, 128 hashed
  word unigram/bigram features, 128 hashed character 3–5 gram features (271
  features per probe; five-probe candidate 1,355). Fixed order, stateless
  extraction, no model ID, persona, provider, latency, token counts, refused
  flag or reasoning text as features. No fitted vocabulary leakage.
- Starting with an empty panel, train an RF for each candidate extension,
  choose highest validation accuracy (ties: macro-F1 then lexicographic ID),
  repeat up to budget. 100 trees, seed 42, balanced class weights, min leaf 1.
  Train uses train only; validation selects the sequence. Calibration and test
  never exported to the trainer. First sweep up to six; chose five by
  validation before test. Comparison of fixed prefixes on test performed after
  choice. Do not change choice based on test. On future datasets use a new
  version and fresh evaluation cohort.
- `random_forest/v2` is trained, registered and Factory-loadable; `review_only`
  cannot mark an identity as accepted. The original v1 ABI and artifact remain
  intact. Existing Stage 2 probe cache reuses Harness answers with matching IDs
  and exact prompt text; standalone RF requests its five probes. It does not
  use the arbitrary initial user response as a sixth feature. Current backend
  mock-judge worker is unchanged; live endpoint does not yet invoke this RF.
- Successful empty responses are retained. Offline replay explicitly sets
  `Observation.completed_blank=True`; old clients still fail on ambiguous empty
  responses, and OpenAI live provider still rejects incomplete/empty output.
  A future live provider must distinguish an observed completed blank from
  failed collection. No provider change made in this release.

## Actual experiment

| Probes | New ID | Validation (51 traces) | Test (102 traces) |
|---:|---|---:|---:|
| 1 | I2 | 74.51% | 72.55% |
| 2 | LM-01 | 82.35% | 81.37% |
| 3 | LM-05 | 92.16% | 86.27% |
| 4 | LM-06 | 92.16% | 86.27% |
| 5 (selected) | I1 | 96.08% | 92.16% |
| 6 | V1-15 | 92.16% | 90.20% |

Frozen five-probe test: 94/102 exact candidates; 101/102 broad-family matches,
macro-F1 .9111; 21 blank test probe responses retained. Llama 3.1 8B recall is
only 1/6, so close versions remain hard. Existing Factory/EvaluationRunner
executed all 102 with no errors and no accepted identities. This is a closed-
set exploratory experiment (all 17 labels seen in train). No unknown-family
accuracy, real deployment drift, or calibrated thresholds claimed.

Reports `reports/rf_panel_experiment/six_probe_selection.json` (all candidate
extensions, validation only), `heldout_results.json` (frozen comparison,
confusion matrix, per-class metrics). RF artifact has its own validation report.
246 test records overlap Harness v1's references and 540 overlap the earlier
raw dataset. This does not leak into our RF train personas, but precludes using
this as independent whole-pipeline benchmark. 2 test personas are the real
unit of persona generalization; 102 traces aren't 102 independent environments.

## Reproduce / extend (Git Bash from repository root)

Install `system/requirements-random-forest.txt` (tested sklearn 1.8.0).
The supplied raw snapshot, fixed split and v2 artifact already exist.

```
python system/run.py training methods
python system/run.py config config/experiments/rf_panel_v2.yaml
python system/tools/evaluate_rf_panel.py --config system/config/experiments/rf_panel_v2.yaml \
  --output local_rf_results.json \
  --selection-report system/reports/rf_panel_experiment/six_probe_selection.json
```

For new raw data register via existing dataset CLI. Choose a complete candidate
pool (IDs with data for every included class) and explicit persona assignments:

```
python system/run.py onboard-dataset split-panel collector_raw/NEW_VERSION \
  --split-id rf_panel_v2 --prompt-set fingerprint_v0 \
  --probe-ids LM-01 LM-05 LM-06 I1 I2 V1-15 \
  --personas config/training/rf_panel_personas.json
```

Adjust the persona mapping to match the data and the exact prompt definitions
in a **copy** of `config/training/rf_panel_candidate.json`. Change dataset ID,
split ID, unused artifact ID (e.g. random_forest/v3), estimator parameters and
budget. The current v2 config is an archival reproduction configuration and
will be blocked from overwriting v2. The general prompt-held-out split is not
compatible with this trainer; plan explicitly blocks it. The other method
strategies remain unavailable.

```
python system/run.py training plan --config config/training/NEW_RF_CONFIG.json
python system/run.py training run --config config/training/NEW_RF_CONFIG.json \
  --method random_forest --approve-dataset --register-candidates
python system/run.py onboard-classifier candidate-config random_forest/v3 \
  --single --output config/experiments/rf_panel_v3.yaml
```

The split tool rejects incomplete panels, duplicate successful probes, missing
model/persona coverage and a persona crossing partitions. Failed attempts can
be excluded only if a matching successful retry is present. Raw records and
old manifests are immutable. Explicit dataset approval is still required;
registration is not production activation. No billable API calls needed.

## Next steps

Collect broader matched panels (e.g. 12–30 diverse approved prompts, enough
personas/configurations for distinct training, selection and holdout groups).
Compare to uniform/random panels, text-only single-response baseline and a
query-budget curve; measure within-family confusions and new-version/family
rejection. Consider adaptive selection conditioned on confused candidates only
after a validated score policy exists. This is a fixed offline greedy panel,
not an adaptive per-request query algorithm or open-set detector. Integrate
LoRA/Harness trainers and the config-driven live worker separately.
