# Quick start — Experiments 5 and 6

From the project root with `scripts/` and `collector/`:

```powershell
python -m pip install -r requirements.txt

# Only if the consolidated data needs to be regenerated:
python scripts/prepare_supervised_data.py --raw-dir ./collector/data/raw --prompts ./collector/prompts/training_prompts.csv --out ./collector/data/supervised --seed 42

# Experiment 5A + 5B (feature families plus category analysis)
python scripts/train_rich_features.py --feature-sets baseline_lr char_lr rich_rf hybrid_lr

# Experiment 5A ablations (optional)
python scripts/train_rich_features.py --feature-sets rich_rf rich_rf_no_lexical rich_rf_no_formatting rich_rf_no_code rich_rf_no_syntax --out ./collector/data/experiment5/ablations

# Experiment 6 (family first, then version, vs direct one-versus-rest)
python scripts/train_hierarchical.py --models baseline_rf baseline_lr
```

Then share these four files to compare results:

- `collector/data/experiment5/features/comparison/feature_validation_metrics.csv`
- `collector/data/experiment5/features/comparison/feature_category_and_model_rates.csv`
- `collector/data/experiment5/hierarchy/comparison/hierarchy_vs_ovr_metrics.csv`
- `collector/data/experiment5/hierarchy/comparison/hierarchy_negative_model_category_rates.csv`

**No test-set evaluation is run.** See README.md for feature ablations, optional sentence embeddings, and methodology.

Optional, classify a single newly collected response after hierarchy training:

```powershell
python scripts/predict_hierarchical.py --target gemini-3.1-pro --algorithm baseline_lr --response-file ./candidate_response.txt
```
