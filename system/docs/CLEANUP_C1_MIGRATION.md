# C1 migration: remove duplicate Stage 1 research scripts

**Approved:** November 22, 2026. **Scope:** 17 copies inside
`system/reference_stage1/scripts/` only. **Not approved:** any other cleanup
proposal, removal of Stage 1 verification, or deletion of root research scripts.

## Why these files existed

Original experiments in the GitHub root `scripts/` train, inspect, compare, and
evaluate Stage 1. When the standalone `system/` subsystem was first packaged,
exact duplicates were copied into `system/reference_stage1/scripts/` to run
parity tests against the original hierarchical predictor without access to the
full repository. The **production verifier does not import these research
scripts**; it loads the 19 checksummed files in `models/stage1_lr/v1/`.

All 17 pairs were verified byte-for-byte identical against the uploaded
`Identities-for-AIs-Fall2026 (2).zip` before deletion. The removed filenames
are listed individually in [`CLEANUP_FILE_INVENTORY.md`](CLEANUP_FILE_INVENTORY.md),
including their research purposes. The root originals remain unmodified.

## Changes made

1. Removed the entire `system/reference_stage1/scripts/` copy (17 `.py` files).
2. Updated `system/tests/test_stage1_real.py` to import
   `../scripts/predict_hierarchical.py` and its sibling research modules when
   `scripts/` exists at the repository root. On a standalone `system/` install,
   the original-source numeric-parity test **skips**; all Stage 1 runtime tests
   still execute.
3. Added `system/tests/test_c1_dedup.py` to guard against reintroducing the
   duplicate scripts and to confirm that Stage 1's versioned artifact remains.
4. Added `system/tools/apply_c1_cleanup.py` to safely remove previously
   installed copies after overlay extraction: dry-run first, verify byte-exact
   correspondence to root originals, then remove only approved copies.
5. Updated `system/README.md`, `system/TBD.md`, the cleanup review/inventory
   and archived implementation notes. No other components were deleted.

## Artifact immutability and provenance

We have **not changed** `system/models/stage1_lr/v1/manifest.json`, any model
weight, or threshold JSON. The historical `provenance.source_script` field in
that immutable manifest still reads
`reference_stage1/scripts/predict_hierarchical.py`, naming the source layout
when `v1` was first released. It is a **historical record, not a runtime
file dependency**. The current canonical, authoritative source in the full
GitHub repository is `scripts/predict_hierarchical.py`. Future releases may
publish updated provenance under a new artifact version. Historical evaluation
reports and hashes are preserved; no results were recalculated or revised.

## Using and testing from your GitHub root (Windows Git Bash)

```bash
source .venv/Scripts/activate
# Required after extracting ZIP over an older checkout: extraction by itself
# leaves removed historical files on disk. Check first, then apply:
python system/tools/apply_c1_cleanup.py
python system/tools/apply_c1_cleanup.py --apply
python system/run.py test
python system/run.py config
(cd system && python -m unittest discover -s tests -p 'test_stage1_real.py' -v)
# Optional: original research tests (requires root scripts/ and dependencies)
python -m unittest discover -s tests -v
```

If the repository has no root `scripts/`, restore that original research
directory from the main project repository—not from a second copy in `system/`.
The parity test will otherwise report a skip and is not a regression. The
operational Stage 1 implementation remains available when explicitly enabled.

## C2–C8

No files or behavior from C2–C8 have been modified or removed. See
[`../CLEANUP_REVIEW.md`](../CLEANUP_REVIEW.md) before proposing any other removal.
