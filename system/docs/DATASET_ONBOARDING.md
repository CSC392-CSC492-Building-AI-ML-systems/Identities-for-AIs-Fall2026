## New fixed-probe split mode

`split-panel` partitions whole personas and checks complete model/persona/sample
coverage for a fixed prompt pool. It intentionally reuses prompt IDs across
partitions, unlike the original general prompt-held-out mode. See
[RF_MULTI_PROMPT.md](RF_MULTI_PROMPT.md) for commands and limitations. Both
protocols preserve blanks without errors and immutable raw snapshots.

# Dataset onboarding — prototype milestone 2

This offline CLI complements `tools/onboard_classifier.py`. It uses the existing
canonical `catalog/models.json` and `datasets/collector_raw/<version>/manifest.json`
convention. No additional database, API service, dependencies, model retraining,
classifier activation, or production authentication are introduced.

## Input contract

Accept a collector ZIP, a snapshot directory containing `raw/`, or the `raw/`
directory itself. Expected layout:

```text
raw/<canonical-model-id>/<prompt-set-version>.jsonl
```

Each JSON object must contain nonblank `record_id`, `model_key`,
`prompt_set_version`, `prompt_id`, `prompt_group`, and `persona_id`, plus
`response_text` and `error` (each string or null). Optional `reasoning_text`
(string or null) and `refused` (boolean or null) are type-checked. All other
fields are preserved, not assumed to be validated. The file path must agree
with the canonical model and prompt-set fields. Unknown catalog IDs, malformed
records, duplicate record IDs, unsafe paths and missing/empty files block
registration. ZIP extraction is restricted to the specified layout, with a 1 GiB
uncompressed input limit and an 8 MiB line limit; no submitted code runs.
This is a local trusted-data tool, not a hardened public file-upload service.

## Workflow (Windows Git Bash, from repository root)

```bash
source .venv/Scripts/activate
python system/tools/onboard_dataset.py --help

# 1. Inspect a new ZIP without modifying the repository.
python system/tools/onboard_dataset.py validate /path/to/new_raw.zip

# 2. Publish under a NEW immutable snapshot version.
python system/tools/onboard_dataset.py register /path/to/new_raw.zip \
  --version 2026-12-01 --source-note 'New collector run; team collection revision XYZ'

# 3. Propose prompt-grouped assignments (no training yet).
python system/tools/onboard_dataset.py split collector_raw/2026-12-01 \
  --split-id candidate_seed42 --seed 42 --weights 60 10 15 15

# 4. Check overlap with prior reference/training collections.
python system/tools/onboard_dataset.py audit collector_raw/2026-12-01 \
  --split-id candidate_seed42 \
  --reference system/models/harness/v1/collector/data/raw \
  --reference system/datasets/collector_raw/2026-11-26/raw

# 5. AFTER reviewing coverage, provenance and overlap, materialize a partition.
python system/tools/onboard_dataset.py export collector_raw/2026-12-01 \
  --split-id candidate_seed42 --partition train \
  --output local_training/train.jsonl
```

The date, archive path and source note above are illustrative. The same CLI
works against the existing November 26 dataset, whose raw manifest is preserved.
Use `--root /path/to/system` **before** the subcommand for alternate checkouts.
JSON summaries are printed to stdout; nonzero exit means refusal. Redirect stdout
to a report file if desired. Registration and split publication use a temporary
sibling directory and an exclusive local lock; existing versions are refused.
Do not modify source files concurrently during operations. Stale locks after a
crash require manual inspection. No external services are contacted.

## Snapshot and split format

```text
system/datasets/collector_raw/<version>/
├── manifest.json           # Raw file hashes, model IDs, counts and provenance
├── README.md
├── raw/                    # Exact input JSONL bytes, including rejected rows
└── splits/<split-id>/
    ├── split_manifest.json # Raw manifest hash, policy, seed, per-partition counts/hashes
    ├── train.jsonl          # Record REFERENCES, not copied response text
    ├── calibration.jsonl
    ├── validation.jsonl
    ├── test.jsonl
    └── excluded.jsonl
```

Quality rules (current policy `include_blank_without_error_v2`): exclude only
rows with non-null `error` from candidate splits. Include null/empty/whitespace
responses without errors and flag them in quality reports. These are behavioral
evidence, not proof of intentional refusal; review provider metadata and parsing.
Do not substitute separate `reasoning_text` for the reply. Preserve every input
row, refusals and repeated exact responses with distinct IDs. `eligible` means
structural eligibility, not scientific, licence or label approval. The previous
policy `exclude_blank_without_error_v1` remains selectable with
`--eligibility-policy`, and old split manifests without a policy field are read
under that original rule. Do not rewrite old manifests or assignments.

Use `python system/tools/onboard_dataset.py inspect collector_raw/2026-11-26
--split-id candidate_include_blank_seed42` (on one command line) to verify a
registered raw snapshot and split and obtain their hashes.

Splitting uses global `prompt_id`, across model, persona, repeat, and prompt-set
version. The collector's `prompt_group` is a source/category, **not** a unique
prompt. Optionally supply `--prompt-aliases aliases.json` containing e.g.
`{"P01":"same-text-group","OTHER_ID":"same-text-group"}`. Map **all** IDs
that should be merged to the same alias; unmapped IDs remain independent.
Raw collector rows do not include original prompt text, so a prompt definition
review is essential to detect cross-ID duplicates or semantic overlap.

The default 60/10/15/15 allocation is applied to the number of **eligible prompt
groups**, not response counts. Groups are stratified by the set(s) of prompt-set
versions they occupy; quotas use largest remainder rounding. A deterministic
SHA-256 ordering with the supplied seed tries up to 128 allocations and keeps
the first one minimizing missing eligible model/partition pairs, stopping at zero.
Only group and label metadata are used, never model predictions. Per-partition
model counts and missing IDs are reported; full coverage is not guaranteed, and
rare models may have very few distinct prompts. Do not repeatedly choose a split
based on test performance. Do not combine independently generated split versions.

The audit compares exact record IDs and prompt IDs against each explicitly
supplied reference directory/ZIP; it accepts older minimal Harness rows. It
reports intersections overall and per partition if a split ID is supplied.
It is not exhaustive: it does not compare prompt text or infer provenance, and
only checks references you provide. Exports verify the raw manifest's inventory,
recompute the deterministic assignments, and check all partition hashes before
writing original JSON objects (one per line). Exports must be outside the source
snapshot and must have a new destination path. Keep them local and uncommitted.

## Actual demonstration on November 26 collection

The recommended new candidate is `candidate_include_blank_seed42`, preserving
`candidate_seed42` and its historical policy. All raw files and the registered
raw manifest remain byte-identical. The v2 split has 9,634 eligible rows and
83 excluded collection errors. The 765 blank replies without errors (633 with
separate reasoning) are retained as eligible. All 17 model identities appear
in each eligible partition.

| Partition | Records | Prompt groups |
|---|---:|---:|
| Train | 5,362 | 199 |
| Calibration | 1,032 | 33 |
| Validation | 1,500 | 50 |
| Test | 1,740 | 50 |
| Excluded | 83 | 3 |

**Not an independent holdout:** the pinned Harness v1 collection shares 795
record IDs, 270 of them in the new test partition, and six prompt IDs. The old
candidate had 393 shared test records. Do not benchmark previously trained models
on these splits without reviewing overlap. The generic split separates the fixed
Harness probes across partitions and does not ensure complete six-probe sessions.
Unknown-family tests and historical training overlap still need separate review.

## Classifier onboarding link

For a new classifier, record `provenance.training_dataset_id`,
`provenance.dataset_manifest_sha256`, and `provenance.split_id` in its existing
artifact manifest, as required by classifier onboarding. Also keep the exact
`split_manifest.json` SHA-256, export digest, code revision, preprocessing,
training/validation/test membership and evaluation report with the training
run. Classifier onboarding verifies the raw manifest digest and, when supplied for a
local dataset, `split_manifest_sha256` and split eligibility policy. A verified
split does not prove the trainer actually used it. The training orchestrator
pins these automatically. No automatic promotion occurs.

## Tests

```bash
python system/run.py test
# Focused tests from system/:
python -B -m unittest discover -s tests/core -t . -p test_dataset_onboarding.py -v
```

No paid API calls or retraining are involved. Production authentication and
confidence-threshold development remain deferred for this prototype.
