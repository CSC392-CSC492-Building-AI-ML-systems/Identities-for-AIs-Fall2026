> November 26 update: C4 and conditional inactive derived-data cleanup are now
> authorized; use the checked helper described in [Legacy Cleanup](LEGACY_CLEANUP.md).
> Historical review below preserves the original dependency findings.

# Detailed cleanup inventory — C1 completed; remaining proposals pending

The uploaded older `system/` directory is **excluded** from this inventory per your instruction. The candidate below is the set of 17 byte-identical pairs between your repository's root `scripts/` and the former `system/reference_stage1/scripts/`. **Uses were reviewed before C1 was approved.** Most are scientific research assets even when the runtime no longer uses them directly.

| File name (was duplicated before C1 cleanup) | What it does | Current reason to retain at least one copy |
|---|---|---|
| `compare_with_ovr.py` | Fairly compares within-family and one-vs-rest classifiers on matching validation observations | Reproduce Stage 1 experimental comparisons |
| `consolidation.py` | Loads collector response records and splits data into prompt-grouped train/validation/test partitions | Rebuild datasets without prompt leakage |
| `embeddings.py` | Optionally extracts sentence-transformer embeddings as experimental features | Reproduce embedding experiment |
| `evaluate_test.py` | Evaluates frozen classifiers on the final untouched test partition | Preserve final metric provenance |
| `experiment_common.py` | Shared response-only feature/validation helpers for Experiment 5 | Keep experimental functions consistent |
| `metrics_common.py` | Common scoring and threshold metrics | Historical calibration reproduction |
| `predict_hierarchical.py` | Runs a four-model family-first detector against one response | Reference implementation for parity tests |
| `predict_one.py` | Single-response prediction with a saved baseline detector | Reproduce legacy inference behavior |
| `prepare_supervised_data.py` | Builds classifier training CSVs from collector JSONL using prompt-separated splits | Recreate training input data |
| `rich_features.py` | Extracts response-only lexical and structural features | Reproduce feature ablations |
| `stylometry.py` | Computes small interpretable stylometric indicators | Baseline stylometric analysis |
| `summarize_validation.py` | Summarizes saved validation predictions and confusion statistics | Historical reporting |
| `train_all_targets.py` | Trains response-only Logistic Regression and RF detectors for several targets | Rebuild original baselines |
| `train_baselines.py` | Trains one-vs-rest TF-IDF LR and RF response-only baselines | Reproduce original baseline comparison |
| `train_hierarchical.py` | Trains family detector and within-family models, compares hierarchy to OVR | Rebuild Stage 1 hierarchy |
| `train_rich_features.py` | Trains and evaluates feature-rich Stage 1 models and category ablations | Reproduce Experiment 5A/5B |
| `train_within_family.py` | Trains within-family pairwise detectors and thresholds | Reproduce sibling-model analysis |

### Other files flagged for review, but NOT redundant by default

- `tests/test_pipeline.py` in the **repository root** checks Stage 1 raw research script behavior and data splitting; `system/tests/test_pipeline.py` tests the new fingerprinting Strategy runtime. They have different assertions despite the same name.
- `tests/test_experiment5.py`, `tests/test_multi_target.py`, `tests/test_within_family.py` protect the original research experiments. The system's tests do not directly replace all these assertions.
- `legacy/prepare_jev_datasets.py` assembles Jev-specific one-vs-rest data with reproducible prompt grouping and experimental output formats. Before deleting or archiving, confirm no old experiment depends on its exact output.
- `cards/cardlib.py` is the **live, authoritative card assembly library** for the UI and M5 history. The copy in `system/models/harness/v1/cards/` belongs to a frozen, checksummed classifier artifact and is *not* an up-to-date replacement.
- `cards/new_model.py`, `cards/check_cards.py`, `cards/show_card.py` respectively create blank model-card YAMLs, validate cards, and display cards for researchers. The M5 read-only HTTP endpoint **does not replace** their editing/validation workflows.
- `collector/collect.py`, `collector/models.yaml` and `collector/licences.yaml` remain sources for response collection, model/provider metadata and licence conditions. The M5 SQLite history does not replace them.
- Root `requirements.txt` and the subsystem's `requirements-*.txt` have different consumers and pinned-version requirements. Do not merge until the research and serving environments are tested in isolation or harmonized.

### How to authorize changes

C1 is approved and completed. See [`CLEANUP_C1_MIGRATION.md`](CLEANUP_C1_MIGRATION.md)
for changes, validation commands, and the retained historical manifest. Other
proposals still require separate approval in [`../CLEANUP_REVIEW.md`](../CLEANUP_REVIEW.md).
