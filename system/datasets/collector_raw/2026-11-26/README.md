# Collector raw snapshot — 2026-11-26

Dataset ID: `collector_raw/2026-11-26`. This is the exact uploaded `raw.zip` collection, not a trained artifact or a new evaluation split. The original JSONL bytes and paths are preserved; [`manifest.json`](manifest.json) records file SHA-256 hashes, counts and comparisons with the pinned Harness reference.

| Prompt set | Files | Records |
|---|---:|---:|
| `fingerprint_v0` | 16 | 6,117 |
| `training_v1` | 4 | 3,600 |
| Total | 20 | 9,717 |

All 17 existing catalog IDs appear across the two sets, representing six families. There are 8,869 nonempty responses with no recorded error, 83 records with recorded errors, and 765 blank responses without a recorded error. No duplicate record IDs or path/model/prompt-set mismatches were found. The term nonempty does not imply a valid or useful training label. In particular, `qwen3.5-9b/fingerprint_v0.jsonl` has 631 blank responses without an error (137 nonempty). Preserve failed/blank rows for audit. Current split policy includes blanks without errors and excludes recorded errors. The new `candidate_include_blank_seed42` split has 9,634 eligible rows. The original manifest and old split remain unchanged for reproducibility. Some rows contain separate reasoning text. Do not substitute it for the observable reply without an explicit research protocol.

From the GitHub root (Windows Git Bash):

```bash
DATA_ROOT="system/datasets/collector_raw/2026-11-26/raw"
ls "$DATA_ROOT"
```

Point training/preparation scripts to this path if they accept a data-root argument; otherwise update their input configuration explicitly. Existing research code may also need prompt YAML, personas, and feature-generation inputs from sibling `collector/`. Do not blindly overwrite that folder: this snapshot lacks `gemini-3.1-pro/fingerprint_v0.jsonl`, which remains in the original pinned Harness bundle. Sixteen model IDs have `fingerprint_v0`; only four have `training_v1`. This archive alone does not establish complete same-session six-probe coverage or train/test separation.

## Updating artifacts after the ML sprint

1. Freeze the exact data snapshot, prompt definitions, preprocessing, training/validation/test split and environment; cite this dataset ID and manifest hash in training provenance.
2. Review collection permissions/licensing and privacy before committing raw records to GitHub. Keep the raw snapshot unchanged; derived splits/features go in separate versioned locations.
3. Check overlaps with old training, reference, calibration and evaluation sets (including reused record IDs and prompt groups); do not treat the new raw collection as an independent holdout.
4. Export new model weights, label maps, feature schemas, thresholds/rejection policy and evaluation report; publish a new version under `system/models/` rather than replacing an old artifact.
5. Build a new Harness reference artifact with its supported-ID list and complete probes, not an in-place overwrite of `harness/v1`.
6. Update `system/models/registry.json` and selected YAML only after parity, readiness and held-out evaluation pass. Existing model artifacts, configurations, historical reports, API schemas and tests remain unchanged in this data-only update.
