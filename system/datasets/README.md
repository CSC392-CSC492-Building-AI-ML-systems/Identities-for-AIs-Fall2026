# Dataset snapshots

Raw training/reference collections are stored separately from pinned inference
artifacts and test fixtures. Current supplied collection:
[`collector_raw/2026-11-26`](collector_raw/2026-11-26/README.md). Keep raw snapshots
immutable and add a new version for a subsequent collection. The offline
[`onboard_dataset.py`](../tools/onboard_dataset.py) CLI supports validation,
registration, reproducible candidate splits, overlap audits and partition exports.
See [Dataset Onboarding](../docs/DATASET_ONBOARDING.md). The November 26 example
split is not a certified holdout. Review privacy and licenses before Git publication.

Current split eligibility includes blank replies without a recorded error. Use
`candidate_include_blank_seed42` for the new experimental split, and keep older
assignment metadata for reproducibility. Historical raw manifest counts are
unchanged; `inspect` reports the selected policy and verified split hashes.
