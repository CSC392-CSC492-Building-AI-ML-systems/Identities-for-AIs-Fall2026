# Checked legacy cleanup — November 26, 2026

The user approved removing obsolete legacy material and inactive derived data
outside raw collections. The checked inventory is based on the older full-repo
ZIP (`Identities-for-AIs-Fall2026 (2).zip`); its outdated `system/` was ignored.
The current release is an overlay with only `system/`, so **the uploaded archive
and your live Git working tree have not been modified**. Run the helper after
merging the new system. It never removes raw data, active integrated artifacts,
card files, pinned Harness references, tests or other source files.

| Group | Path | Files | Purpose / dependency |
|---|---|---:|---|
| legacy | `legacy/prepare_jev_datasets.py` | 1 | Old Jev OVR preparation; not used by integrated runtime. Exact older experimental reproduction may be lost; preserve via Git history or backup. |
| experiment5 | `collector/data/experiment5/` | 105 | Feature experiments, model files and reports; original `predict_hierarchical.py`, `train_hierarchical.py`, `train_rich_features.py` use this location. Integrated Stage 1 uses its own registered v1 bundle. |
| supervised | `collector/data/supervised/` | 67 | Prepared research CSVs/manifests; used by historical training/evaluation and regenerate via `prepare_supervised_data.py`. |
| supervised_results | `collector/data/supervised_results/` | 54 | Older fitted models, thresholds and metrics; baseline training, evaluation, summary and comparison scripts use this location. |
| within_family_results | `collector/data/within_family_results/` | 35 | Older within-family models/metrics used by original comparison/training code. |

These 261 derived files (~202.6 MB decimal) are not input paths to the current
integrated artifact registry/runtime, but we cannot know whether teammates are
using them in ongoing research. Preserve any active experiment or unique
required results. Back up before deletion; Git history may not contain untracked
files. Deletion does not change or repair the original research scripts, which
may require those data/results to be regenerated before running. No claim of
exact historical regeneration has been made. Pinned Stage 1 and RF artifact
weights, original runtime fixtures, dataset split index metadata, and Harness
reference rows remain intact.

## Commands from repository root

```bash
# Preview known files across all groups (refuses modified/unreviewed files)
python system/tools/apply_legacy_cleanup.py
# Apply obsolete Jev script cleanup
python system/tools/apply_legacy_cleanup.py --group legacy --apply
# Apply historical derived-data cleanup ONLY after verifying inactive use with team
python system/tools/apply_legacy_cleanup.py --group experiment5 --group supervised \
  --group supervised_results --group within_family_results --confirm-inactive --apply
# Review Git status and commit the intended deletions yourself
 git status --short
```

Select fewer groups if some are active. The tool checks exact byte sizes and
SHA-256 against `LEGACY_CLEANUP_INVENTORY.json`, rejects unreviewed files,
symlinks/junctions or changes, and performs a preflight of all selected groups
before deletion. It does not remove entire trees blindly; only known files and
empty directories. Missing files are a no-op. It cannot prove inactivity or
provide transactional rollback on concurrent filesystem changes. Stop all team
processes and work in a clean backed-up checkout before applying. The explicit
`--confirm-inactive` flag is a safeguard, not additional blanket approval.

The actual older snapshot was extracted into a temporary test directory; the
helper removed all 262 matching files, while protected control raw/system files
remained. The original ZIP remains available as backup. No other cleanup
proposals are applied. Future consolidation into `system/`, `tests/` and `cards/`
requires migration of imports, scripts, collector paths and test discovery.
