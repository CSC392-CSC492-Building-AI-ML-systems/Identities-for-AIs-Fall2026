# Current cleanup decision — November 26, 2026

C1 stays completed. User now approved removal of obsolete legacy material and
inactive derived data. C4 Jev script is eligible for the checked root cleanup;
four derived-data groups are conditional on confirmed inactivity because old
research scripts still consume them. See `docs/LEGACY_CLEANUP.md` and the exact
hash inventory. The current system-only ZIP cannot itself delete root files;
the helper has been exercised in a temporary snapshot. Active raw collections,
pinned model/reference files, test fixtures and all remaining C2–C3/C5–C8
components stay unchanged. No root folder moves are applied. Older review below
is retained as historical evidence, superseded where applicable.

---

# Cleanup status — C1 approved and completed; C2–C8 unchanged

Detailed per-file uses for the 17 exact Stage 1 duplicates and other reviewed files are in [`docs/CLEANUP_FILE_INVENTORY.md`](docs/CLEANUP_FILE_INVENTORY.md).

Review of the **uploaded repository outside its old `system/` directory**, compared with the latest separately maintained Milestone 4/5 `system/`. The uploaded repository's `system/` directory was explicitly excluded from this review because it is out of date. Paths below are relative to your GitHub root.

**Only C1 has been approved and applied:** the 17 duplicate Python files previously at
`system/reference_stage1/scripts/` were removed. The originals in the
repository-root `scripts/` are retained, and the Stage 1 classifier remains
operational. C2–C8 have **not** been removed or approved. All further cleanup
still requires explicit approval. See [`docs/CLEANUP_C1_MIGRATION.md`](docs/CLEANUP_C1_MIGRATION.md).

| ID | Files or directory | Current purpose | Overlap / findings | Safe recommendation / required migration | Approval |
|---|---|---|---|---|---|
| C1 | `scripts/*.py` (17 files) vs `system/reference_stage1/scripts/*.py` (17 files) | Original Stage 1 research training, prediction, evaluation scripts; system's copy supports inference parity tests and artifact provenance | **All 17 pairs were byte-identical before removal; only root `scripts/` remains** | **Completed:** root `scripts/` is authoritative; system parity tests now import it when present, and released manifest provenance remains immutable. | [x] Approved C1 (Nov 22, 2026) |
| C2 | `system/models/harness/v1/cards/` vs root `cards/` | The Harness artifact bundles a **pinned** version of its own card library and data, while root `cards/` is the team's current authoritative library | 27 identical, **26 differing** files in snapshot (including `cardlib.py` and many YAML cards); cannot treat as redundant | **Keep both for now.** M5 reads root `cards/`; Harness v1 must remain immutable/checksummed. A future `harness/v2` could share current card loading with explicit reproducible snapshots. | [ ] Pending |
| C3 | Root `tests/` vs `system/tests/` | Root tests verify Stage 1 research scripts and data preparation. System tests verify pipeline, model artifacts, Factory and backend. | Some same basenames, **not equivalent content** (`test_pipeline.py` differs) | **Keep both.** Later consolidate test discovery and update paths before pruning. | [ ] Pending |
| C4 | `legacy/prepare_jev_datasets.py` | Reproduces Jev one-vs-rest prompt-group data preparation, including dataset splits | A separate older dataset workflow; no demonstrated replacement with identical inputs/outputs | Consider archive under `docs/legacy/` or remove only after confirming Jev experiments are fully reproducible through a supported replacement. | [ ] Pending |
| C5 | Root `requirements.txt` vs `system/requirements-*.txt` | Root requirements support Stage 1 research; subsystem requirement files support integrated inference and FastAPI | Similar dependencies but different version constraints, including incompatible sklearn serialization histories | **Keep** until dependency ownership and environment isolation are documented and verified. | [ ] Pending |
| C6 | `cards/new_model.py`, `cards/check_cards.py`, `cards/show_card.py` | Onboarding scaffolding, data-quality checks, and human CLI inspection for published model cards | M5 adds only **read-only HTTP access**; it does not replace these tools | **Keep**; they are not duplicates of the new API. | [ ] Pending |
| C7 | `collector/collect.py`, `collector/models.yaml`, `collector/licences.yaml` | Source-of-truth data collection, model routing/config and licence metadata | Referenced by root cards and research. They are not duplicated by M5 history | **Keep**. No deletion recommended. | [ ] Pending |
| C8 | Legacy synchronous/mock backend endpoints in `system/backend/app.py` | Test scaffolding and opt-in local live analysis; mock endpoints remain useful for CI | Overlap with newer authenticated live jobs; mock routes are unauthenticated and unsafe for public deployment | Keep during development. Before removing or restricting, migrate tests and examples, and define a production router separation. Require separate approval. | [ ] Pending |

### Suggested approval sequence

1. C1 completed: keep repository-root research scripts; do not recreate internal copies.
2. Review C2 only once Harness artifact versioning and its reference-card semantics are settled; snapshots are not interchangeable.
3. Review C4 only after asking the original experiment owners whether its outputs must remain reproducible.
4. Leave C3, C5, C6 and C7 in place for now because their responsibilities differ. Reconsider C8 after the production security architecture is ready.

**Approval recorded:** C1 only (retain root scripts, remove the 17 internal copies). C2–C8 remain pending.
