# Repository consolidation — current layout

## Scope and source snapshots

The latest integrated `fingerprinting_system_release_workflow.zip` is the source of `system/`. The sibling collector, authoritative cards, Stage 1 scripts and original tests come from the previously supplied `Identities-for-AIs-Fall2026 (2).zip`. The old `system/` inside that repository snapshot was not used. Newer local teammate/frontend work is not represented unless supplied in these inputs. This is a clean root snapshot, not a patch to a live Git checkout.

## Moves and removals

| Previous location | Current location |
|---|---|
| `collector/` | `system/collector/` (configuration, licence library, prompts, collector source, raw data) |
| `scripts/` | `system/research/stage1/` (deferred research; derived output defaults now `system/.local/stage1/`) |
| `system/tests/` | `tests/core/` except real historical Stage 1 tests in `tests/research/` |
| Original root `tests/` | `tests/research/` (preserved; no collision with core test_pipeline) |
| `system/testdata/` | `tests/fixtures/` (evaluation/replay fixtures, not training data) |
| Root Stage 1 guides and requirements | `system/research/stage1/docs/` and `requirements/` |
| `cards/` | Unchanged location; card library now resolves `system/collector/` |
| `system/requirements-*.txt` | Existing locations retained to keep setup commands working |

The old root `legacy/` and collector derived-data folders `experiment5`, `supervised`, `supervised_results`, `within_family_results` are omitted. The original source ZIP remains the backup. Research scripts that used derived data must regenerate it before use. The pinned Harness reference bundles, RF/LoRA/Stage 1 registered weights, raw versioned snapshots, split assignments, and all six evaluation fixtures are preserved. Do not deduplicate the versioned artifact bundles by replacing their pinned source/data with mutable collector files. The old RF feature extractor is byte-pinned; its legacy standalone preparation defaults are unchanged, so supply explicit input/output paths if using that historical script. The active RF panel trainer does not use that preparation workflow. See `REPOSITORY_CONSOLIDATION_INVENTORY.json` for omitted legacy files and their checksums. Historical cleanup tools refer to pre-consolidation layouts and are retained for migration verification; do not run them against the new layout expecting current data cleanup.

Local environments, caches, Git history, `.env` credentials, job databases and unpublished runs are intentionally not distributed. No existing Git history is rewritten.

## Safe adoption into your working repository

1. Stop API and worker processes. Commit/stash or back up local changes, and back up any unique experimental results or frontend work. Preserve existing local DBs, encryption keys, credentials and virtual environments separately; never commit secrets. Use a new branch/worktree or a fresh folder for the consolidation.
2. Extract the root ZIP into an **empty directory** first. Verify the three top-level directories and run the quick-start commands from its root. Do not simply overlay it onto the old repository: that would leave the old root collector/scripts, system/tests/testdata, and legacy data behind.
3. In a migration branch, compare the extracted files with your actual checkout. Move/replace the managed files deliberately, merge newer teammate edits, and remove the old tracked paths only after verifying their replacements and checking the inventory. Remove the listed obsolete data only if your team no longer needs it. Preserve any unique files not present in the supplied snapshots. Do not delete `.git`, local credentials, or newer unrelated code. The root release does not contain an automated destructive migration.
4. Review `git status` and `git diff --stat`, rerun tests, and commit the migration as one reviewed change. Keep the pre-migration branch for recovery.

## Run from repository root (PowerShell)

```powershell
python -m pip install -r system/requirements-integrated.txt
python -m pip install -r system/requirements-backend.txt
python system/run.py config config/experiments/live_stage2_review.yaml --require-ready
python system/run.py test
python system/run.py test --research  # optional deferred research including real Stage 1 parity
python system/collector/collect.py --model mock-model --dry-run --limit 1
python system/run.py onboard-model status
python cards/show_card.py --family Llama
python system/tools/demo_stage2_replay.py
```

Filtered tests: `python -B -m unittest tests.core.test_backend_stage2 -v`. `python system/run.py test --all` runs both suites. The launcher keeps paths relative to `system/` for commands other than testing; the test runner now discovers root tests and imports established packages without writing caches into immutable artifact directories. Historical documents and reports may mention the previous paths. Active backend/API contract and classifier configuration are unchanged. A real LoRA training run, authorized live provider/judge checks, blank transport semantics and frontend demonstration remain pending; no Stage 1 work is required for the prototype.
