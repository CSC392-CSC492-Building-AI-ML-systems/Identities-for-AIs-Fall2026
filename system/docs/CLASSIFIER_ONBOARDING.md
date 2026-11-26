## RF panel ABI extension

The onboarding checker now accepts `fingerprint_rf_panel_text_v1` alongside the
original 52-feature ABI. It validates the exact installed feature implementations,
ordered probe text/IDs and feature columns, and requires `review_only`.
See [RF_MULTI_PROMPT.md](RF_MULTI_PROMPT.md). The published v2 candidate is
selectable but not automatically activated.

# Classifier onboarding — candidate bundle workflow (prototype)

This milestone adds an offline CLI around the **existing** manifest schema,
model catalog, registry, adapter constructors and unified evaluation runner.
It does not train models, ingest datasets, implement thresholds, modify the
backend, or automatically activate new artifacts. No account/production auth
work is included. The current HTTP live worker still runs the mock-judge
Harness-only workflow; merely changing a YAML file does not make that worker
run the updated ML cascade. Connecting approved classifiers to the live worker
is a separate backend milestone.

## 1. What teammates submit

Each teammate supplies an **extracted directory** (unzip a trusted bundle yourself),
with `manifest.json` at the top and all required payload files listed in its
`required_files`. Use unique canonical IDs from `catalog/models.json`. Do not
submit API keys, `.env` files, credentials, logs, or private/unauthorized data.
The tool handles directories only; it does not extract arbitrary ZIP files.

| Adapter | Example candidate | Required payloads / current contract |
|---|---|---|
| Stage 1 Logistic Regression | `stage1_lr/v2` | Family/conditional/OVR joblibs and per-approach threshold JSON as in v1. Current adapter hard-codes the original four Gemini/Llama models; six-family expansion requires an adapter upgrade. |
| LoRA | `lora/v3` | `adapter_model.safetensors`, `adapter_config.json`; Qwen2.5 sequence-classification checkpoint, correct class order and trained score head, pinned HF commit, tokenizer/preprocessing compatible with existing loader. |
| AI Harness | `harness/v2` | Versioned `agent/`, `cards/`, `collector/` runtime dependencies, prompts and references. Existing legacy `identify_api` interface, exactly six probes, literal source model mapping, sample_index 0/1 only; do not include test rows or the entire raw update as references. |
| Random Forest | `random_forest/v2` | `classifier.joblib`, `feature_manifest.json`, `feature_extractor.py`; sklearn pipeline with correct class order and exact 52-feature ABI/feature source; a different extractor or feature count requires an adapter upgrade. |

For all bundles, include source/training code revision, dataset ID, SHA-256 of
its dataset manifest, split ID (the exact train/validation/test membership should
be archived separately), dependency versions, supported model identities and
method-specific options. Provide actual training/evaluation reports and the
notebook or scripts to the team; optionally include sanitized evidence files in
the manifest inventory. Provenance is a teammate declaration, not proof of
correctness. Raw dataset `collector_raw/2026-11-26` is unreviewed, not an already
validated split. Do not claim a model trained on it unless that is true.

Example folder:

```text
rf_submission/
  manifest.json
  classifier.joblib
  feature_manifest.json
  feature_extractor.py
```

## 2. Create a manifest template (from GitHub root, Windows Git Bash)

```bash
source .venv/Scripts/activate
python -m pip install -r system/requirements-integrated.txt
python system/tools/onboard_classifier.py template \
  --from-artifact random_forest/v1 --artifact-id random_forest/v2 \
  --output rf_submission/manifest.json
```

This copies only the existing manifest structure/options and expected filenames,
not the old weights or evidence. Replace every TODO and correct every option and
file list to match the submitted model. Fill in the new model's real class order,
feature ABI, source and dependencies. `required_files[].sha256: null` means the
CLI computes it; if a digest is supplied it must match the copied bytes. Include
all payload files; unlisted files, unsafe paths, symlinks, duplicate case-insensitive
paths and overwrites are refused. Templates are not approved releases.

For the newly bundled dataset, retrieve its manifest digest (not the raw archive
digest) with:

```bash
sha256sum system/datasets/collector_raw/2026-11-26/manifest.json
```

`provenance` example (replace all values with actual evidence):

```json
{
  "source": "teammate's RF training export",
  "training_dataset_id": "collector_raw/2026-11-26",
  "dataset_manifest_sha256": "<actual 64-character lowercase SHA-256>",
  "split_id": "<actual frozen split ID>",
  "training_code_revision": "<actual Git commit or notebook digest>",
  "runtime_dependencies": {"python": "3.11", "scikit-learn": "1.8.0"}
}
```

If the matching dataset manifest is available locally, its digest must agree.
Otherwise validation explicitly warns that external provenance is unverified.
LoRA additionally requires `options.label_order_status` to be `confirmed` or
`provisional_unconfirmed`. For `confirmed`, cite the real training label mapping
in `provenance.label_order_evidence`. This is a declaration to review; it is not
an independent parity test. Unconfirmed label mappings withhold named candidates.
Keep LoRA and RF in `review_only` pending the deferred acceptance-policy work.

## 3. Validate without registering

```bash
python system/tools/onboard_classifier.py validate rf_submission
```

The CLI stages a private copy, checks the full inventory and digests, runs the
existing registry metadata/readiness checks and method-specific static checks.
It reports `metadata_checked`, `runtime_validated: false`, `activated: false`.
It does **not** deserialize joblib, execute submitted Harness code, download base
weights, or make network calls. A structurally valid joblib file can still be
invalid or malicious; the checker intentionally cannot prove its contents.

## 4. Register a reviewed team-owned candidate

```bash
python system/tools/onboard_classifier.py register rf_submission --trust-bundle
```

Only do this for trusted, team-owned files reviewed by a developer. Joblib and
Harness source are executable when the real adapter runs; a checksum proves
integrity, not safety. The tool generates the checksummed immutable candidate
manifest and adds `models/random_forest/v2/` and its index entry in
`models/registry.json`. It never edits old artifact directories or `production.yaml`.
The local lock prevents concurrent writers using this tool; registry replacement
is atomic, with rollback on ordinary write failure. A hard crash can leave an
unindexed directory or stale lock; inspect the files and coordinate with other
writers before manually recovering. Do not run parallel manual registry edits
or publish from a shared network filesystem. Commit the candidate manifest and
registry entry together; store bulky files in agreed artifact storage if needed.

## 5. Evaluate the candidate with the existing Factory

```bash
python system/tools/onboard_classifier.py candidate-config random_forest/v2 \
  --single --output system/config/experiments/rf_v2_candidate.yaml

python system/run.py config config/experiments/rf_v2_candidate.yaml --require-ready

# run.py interprets relative paths from system/, not repository root
python system/run.py evaluate --config config/experiments/rf_v2_candidate.yaml \
  --cases /absolute/path/to/heldout_cases.jsonl --scope stage2 \
  --methods random_forest --output reports/calibration/rf_v2_candidate
```

`--single` selects only the new Stage 2 method, disabling Stage 1. Without it the
candidate replaces the corresponding adapter selection in a copy of the base
configuration (defaults to production). For Stage 1, use `--approach` if the
candidate does not support the default approach, then evaluate `--scope stage1`.
Use normalized cases from the unified evaluation format, not raw collector JSONL.
See `UNIFIED_EVALUATION.md`. Do not compare methods on different data splits as
if they were a common test. A completed report does not guarantee acceptable
accuracy; inspect blocked/error scopes and run trusted inference on a dedicated
holdout. Harness mock is plumbing only; an explicitly authorized live judge is
required for real Harness evaluation.

## 6. Review and activate later (not automated)

Compare candidate vs previous version using frozen validation and test cohorts.
Verify actual runtime loading, feature order, model labels, errors, known/unknown
behavior, latency and card associations. The candidate config is a research
selection, not a production approval. After the team explicitly approves the
artifact and policy, update the relevant production config in a reviewed PR;
retain older versions for rollback. The HTTP worker still needs the real
config-driven inference path before a production config affects the frontend.

## Tests and limits

Run from repository root:

```bash
(python -m unittest discover -s tests/core -t . -p 'test_classifier_onboarding.py' -v)
python system/run.py config --require-ready
```

Tests cover the real registry/config loader, missing/extra files, checksums,
wrong model identities, provenance, no overwrite, review-only guard, feature ABI,
locking/rollback, and non-deserialization. This is a **prototype local tool** for
trusted submissions, not a sandbox, a remote model upload service, a signature
verification service, or an automated scientific promotion gate.

### Validation of this implementation

22 onboarding tests and 128 related tests (including those 22) passed in the
packaging environment. Existing production file-readiness also passes. A temporary
registry with a **copy** of the existing RF checkpoint registered under a test
version successfully ran the real standalone evaluator; it was not published
and is not a new training experiment. All four adapter bundles were checked
structurally using temporary copies. LoRA base weights and real judge API calls
were not run. The full system regression suite was not rerun for this additive
change. Existing Stage 1 scikit-learn serialization version warnings remain.

If using the additive update ZIP, it includes only the new CLI, module, tests and
this guide. Merge the onboarding items from the separately supplied updated
TBD.md into your team's active backlog, and add `models/.onboarding-*/` and
`models/.onboarding.lock` to `system/.gitignore` if not already present. The full
ZIP includes those documentation/ignore changes; it is based on the last M6
data-update package, not teammates' unshared local edits.

## Training orchestration refinement (November 26)

New templates can bind an existing verified dataset and split without manual hash
copying: add `--dataset collector_raw/2026-11-26 --split-id
candidate_include_blank_seed42` to `template`. The remaining training provenance
fields still require actual teammate evidence. If a local split hash is declared,
validation reconstructs split assignments, checks the digest and eligibility policy.
Old manifests without the split hash retain the original validation behavior.
The new orchestrator invokes this same onboarding implementation; see
[Training Orchestrator](TRAINING_ORCHESTRATOR.md). Neither registration nor a
verified split is proof of trained weights, independent evaluation or activation.
