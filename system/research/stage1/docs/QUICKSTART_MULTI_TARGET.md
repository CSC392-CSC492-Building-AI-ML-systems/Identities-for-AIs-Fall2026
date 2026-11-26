# Four-model one-versus-rest classifiers — quick start

This package **replaces** the original supervised-fingerprinting starter. It includes all consolidation and model-training code from the earlier package plus two new scripts:

- `scripts/train_all_targets.py`: trains the other three (or all) one-vs-rest detectors.
- `scripts/summarize_validation.py`: aggregates existing validation predictions, including errors by actual negative model, without retraining.

## Already ran Gemini 3.1 Pro? Start here

Copy these scripts to your project, preserving the `scripts/` directory, then from the project root:

```powershell
# Reuse existing prepared CSVs and Gemini 3.1 Pro saved predictions.
# Train both classifiers for the OTHER three models:
python scripts/train_all_targets.py --exclude gemini-3.1-pro

# Optionally regenerate reports without retraining:
python scripts/summarize_validation.py --require-all
```

Your prepared data should exist in `collector/data/supervised/` and original Gemini results in `collector/data/supervised_results/gemini-3.1-pro/all_personas/`. The runner discovers the other model IDs from `collector/data/supervised/summary.json` and trains them independently, labeling only that target `1` and all others `0`.

## Working in a fresh branch? Rebuild the data first

```powershell
python -m pip install -r requirements.txt
python scripts/prepare_supervised_data.py --raw-dir ./collector/data/raw --prompts ./collector/prompts/training_prompts.csv --out ./collector/data/supervised --seed 42
python scripts/train_all_targets.py
```

When no `--exclude` is provided, this trains all four targets or reuses any valid existing outputs.

## Outputs to inspect

For every target, find its original prediction CSVs under:

`collector/data/supervised_results/<target>/all_personas/`

- `rf_stylometry_validation_predictions.csv`
- `lr_tfidf_validation_predictions.csv`
- `validation_metrics.csv`

Across all targets, find comparison reports under `collector/data/supervised_results/comparison/`:

- **`negative_model_rates.csv`**: negative-model false acceptance rates and detection rates by target, algorithm and threshold.
- **`negative_acceptance_matrix.csv`**: matrix of the percentage of each alternative model incorrectly classified as the target (CSV values 0 to 1).
- **`baseline_false_alarm_rates.csv`**: genuine target-model false alarms.
- **`overall_validation_metrics.csv`**: overall ROC-AUC, balanced accuracy, recall, etc.
- **`all_validation_predictions.csv`**: all scores and predicted labels together.

Two threshold rules are reported: `fixed_0.5` and `validation_false_alarm_limit`. Do not compare one model's rates at 0.5 with another model's optimized-threshold rates without stating this distinction.

The **test split stays untouched** during these runs. These reports are intended for validation-based model selection; perform final test evaluation only after freezing the classifiers and thresholds.

For full setup, rationale, and future agentic approach, see `README.md`.
