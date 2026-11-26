# Single-response LLM fingerprinting — independent supervised branch

This package is a **standalone** alternative to the previous Jev few-shot experiments. It includes **data consolidation** from the original collector JSONL files, **two supervised binary classifiers**, **validation reports**, **explicit final-test evaluation**, and **single-response inference**. No Jev SDK or API key is needed.

> Primary research goal: given a **single response** (and a baseline model whose identity is already known), classify whether the response is **consistent with that baseline**. This is a closed-world one-versus-rest training task; it is **not proof of model identity**, nor evidence of performance against every possible unknown model.

## Files included

```text
supervised_fingerprinting/
├── README.md
├── requirements.txt
├── scripts/
│   ├── consolidation.py         # Original collector parsing and deterministic split helpers
│   ├── prepare_supervised_data.py # Rebuild datasets from raw model folders and prompt CSV
│   ├── stylometry.py            # Interpretable response-only feature extractor
│   ├── metrics_common.py        # Evaluation + false-alarm thresholding
│   ├── train_baselines.py       # Random Forest + TF-IDF Logistic Regression
│   ├── evaluate_test.py         # Explicit final held-out test run
│   └── predict_one.py           # Apply trained classifier to a new response
└── legacy/
    └── prepare_jev_datasets.py  # Original complete consolidation/refs script for reproducibility
```

`legacy/prepare_jev_datasets.py` is included so the prior data preparation code is preserved verbatim. **You do not need to run it**: `prepare_supervised_data.py` generates the necessary merged and labeled data without Jev-specific reference files. The split helper logic is copied directly from the prior script, preserving the seed-42 prompt/category partition used in earlier experiments.

## 1. Start a new Git branch

From the project root containing `collector/`:

```powershell
git switch -c experiment/supervised-fingerprinting
python -m pip install -r requirements.txt
```

Copy the package's `scripts/` folder and `requirements.txt` to your new branch's root, or keep this package in a `supervised_fingerprinting/` subfolder and prefix all commands with that folder name. Commands below assume scripts are under `scripts/` at the project root.

**Expected source layout**:

```text
project-root/
├── collector/
│   ├── prompts/
│   │   └── training_prompts.csv
│   └── data/
│       └── raw/
│           ├── gemini-3.1-pro/training_v1.jsonl
│           ├── gemini-3.8-flash/training_v1.jsonl
│           ├── llama3.1-8b/training_v1.jsonl
│           └── llama3.2-3b/training_v1.jsonl
├── scripts/   # from this package
└── requirements.txt
```

If you have more or fewer model folders, the consolidation script discovers those present. The original 4-model run recorded 3,598 usable responses from 300 prompts: gemini-3.1-pro (900), gemini-3.8-flash (898), llama3.1-8b (900), llama3.2-3b (900). Two empty responses were dropped. These counts are **expected based on your prior summary**, not a guarantee about a new collection.

### Install dependencies

```powershell
python -m pip install -r requirements.txt
```

## 2. Re-consolidate from the base files (no Jev dependency)

```powershell
python scripts/prepare_supervised_data.py `
  --raw-dir ./collector/data/raw `
  --prompts ./collector/prompts/training_prompts.csv `
  --out ./collector/data/supervised `
  --seed 42 `
  --expected-models 4
```

For a one-line alternative:

```powershell
python scripts/prepare_supervised_data.py --raw-dir ./collector/data/raw --prompts ./collector/prompts/training_prompts.csv --out ./collector/data/supervised --seed 42
```

The script scans `raw/*/training_v1.jsonl` and joins the `prompt_id` from each JSONL record to the prompt CSV's `source_id`, recovering `prompt_text` and prompt metadata. It automatically handles the title row in the CSV. It ignores collection errors and empty responses and rejects unknown prompt IDs. It creates one shared split per prompt ID, **not per response**, with category-stratified target proportions of 70% development, 15% validation, and 15% test. Same seed + same prompt IDs + same category metadata => same assignments as earlier Jev runs. Changing the prompt population/categories may change the split.

Files written:

```text
collector/data/supervised/
├── summary.json
├── data/
│   ├── all_responses.csv
│   ├── all_responses.jsonl
│   └── prompt_assignments.csv
├── splits/
│   ├── development.csv
│   ├── validation.csv
│   └── test.csv
├── views/
│   ├── all_personas/{development,validation,test}.csv
│   └── persona_P13/{development,validation,test}.csv  # also BK1, P05 by default
└── binary/
    ├── gemini-3.1-pro/all_personas/{development,validation,test}.csv
    ├── gemini-3.8-flash/all_personas/{development,validation,test}.csv
    ├── llama3.1-8b/all_personas/{development,validation,test}.csv
    └── llama3.2-3b/all_personas/{development,validation,test}.csv
```

`binary/<target>/...` labels **every response from that target `1`** and every response from all other models `0`. For example, gemini-3.1-pro vs the other three models is **one detector**, not a four-way classifier. You do not have to use all four targets.

**Leakage safeguards**: all model responses and repeated samples to the same prompt stay in the same partition. Training uses the response's text only; it never uses `model_key`, `prompt_id`, `persona_id`, token counts reported by the model/provider, or the true label as a feature. Those fields are retained for evaluation and dataset auditing.

## 3. Train one target-model detector (first attempt)

```powershell
python scripts/train_baselines.py --data-root ./collector/data/supervised --target gemini-3.1-pro --models rf lr
```

This trains two models, independently:

- **`rf_stylometry`**: a Random Forest trained on ~36 explicit features such as response length, paragraph/sentence counts, vocabulary variety, punctuation ratios, Markdown headings/bullets/code blocks and hedging rates. Feature importances are written to CSV; they are associative, **not causal**.
- **`lr_tfidf`**: Logistic Regression trained on TF-IDF word unigrams/bigrams and character 3–5 grams. The fitted vocabulary and learned coefficients are saved alongside the model; features emphasize text patterns rather than human-chosen counts.

Both use class weighting because a target contributes about one quarter of the data. They get **all available development responses**, rather than 4+4/8+8 references per API call.

The script reports validation ROC-AUC, change detection rate, and baseline false-alarm rate. It writes:

```text
collector/data/supervised_results/gemini-3.1-pro/all_personas/
├── rf_stylometry.joblib
├── rf_stylometry_threshold.json
├── rf_stylometry_validation_predictions.csv
├── rf_stylometry_validation_by_group.csv
├── rf_feature_importance.csv
├── lr_tfidf.joblib
├── lr_tfidf_threshold.json
├── lr_tfidf_validation_predictions.csv
├── lr_tfidf_validation_by_group.csv
├── lr_top_coefficients.csv
├── validation_metrics.csv
└── training_settings.json
```

To train another **independent target**, change `--target`. To run only the Random Forest, use `--models rf`. To run only regression, use `--models lr`.

### What the scores mean

The classifier outputs a target score. The **positive class** is the baseline model. It predicts the baseline for `score >= threshold` and flags a **possible change** otherwise. The score may not be calibrated as a literal probability.

Two threshold rules are reported on validation:

1. `fixed_0.5` (simple baseline).
2. `validation_false_alarm_limit` (chosen to reject at most 10% of genuine baseline validation responses, using the largest feasible threshold). You can change this by setting `--max-false-alarm 0.05`, etc.

False alarm = *baseline response classified as changed* = **false negative (FN)** under the target-model-positive convention. Missed change = *other model accepted as baseline* = **false positive (FP)**. Accuracy alone is misleading when 75% of cases are negative, so compare **ROC-AUC, balanced accuracy, true change-detection rate, and false alarm rate**. The threshold is **tuned on validation only**, not the final test set.

You can optionally train a persona-specific study without changing the data split:

```powershell
python scripts/train_baselines.py --target gemini-3.1-pro --view persona_P13 --models rf lr
```

But note that persona-specific subsets contain less data. Compare across a common evaluation population when making persona-ablation claims.

## 4. Compare validation results before using the test set

Open `validation_metrics.csv`, `rf_feature_importance.csv`, `lr_top_coefficients.csv` and the group breakdowns. Look for:

- Better **ROC-AUC** (ranking genuine baseline responses above alternatives).
- Better **change-detection rate** at a tolerable baseline false-alarm rate.
- Which negative model or prompt category is hardest to reject.
- Whether feature importances are dominated by response length, format or generic topical phrases.

**Selection rule**: decide on the preferred classifier/threshold *before* final test. Training scripts deliberately do not read the final test partition.

## 5. Evaluate the final held-out test (explicit action)

After selecting a classifier and freezing its threshold, choose one of:

```powershell
python scripts/evaluate_test.py --target gemini-3.1-pro --algorithm rf_stylometry
```

or

```powershell
python scripts/evaluate_test.py --target gemini-3.1-pro --algorithm lr_tfidf
```

Outputs: `<algorithm>_test_metrics.csv`, `<algorithm>_test_predictions.csv`, `<algorithm>_test_by_group.csv`. The script refuses to overwrite a prior test result unless you explicitly use `--allow-overwrite`. Do **not** use test results to tune the classifier; if you need additional research tuning, return to development/validation or collect a new final holdout.

## 6. Apply the model to one new response

```powershell
python scripts/predict_one.py `
  --model ./collector/data/supervised_results/gemini-3.1-pro/all_personas/rf_stylometry.joblib `
  --threshold-file ./collector/data/supervised_results/gemini-3.1-pro/all_personas/rf_stylometry_threshold.json `
  --response-file ./new_response.txt
```

This returns a score and one of `consistent_with_baseline` or `possible_model_change`. **The final deployed classifier makes a decision about one response**, without needing to resend training references or use Jev.

Do not load `.joblib` models from untrusted sources; Python model artifacts may execute code when deserialized.

## 7. Next research direction: an agentic classifier (separate experiment)

An **agentic** alternative can be studied after a statistical baseline exists. One design uses a controller to (1) extract objective features, (2) ask specialized judges to examine prompt adherence, structure and writing behavior, (3) check those claims against the actual text, and (4) aggregate evidence into a final baseline-vs-change decision. Save each judge's outputs to allow auditing.

The important constraint is **Stage 1 only receives one prompt-response pair**. If an agent queries the suspicious model repeatedly, that becomes the multi-query Stage 2 task and should be measured separately. An agent is not automatically more accurate or better calibrated; evaluate it on the **same prompt-grouped validation/test data**, with identical positive/negative definitions, and compare runtime/API cost. You can also test agent-derived behavioral features as inputs to a supervised classifier, rather than accepting an agent's final identity judgment.

## 8. Caveats and reproducibility

- Results will depend on the **specific versions and generation settings** represented in the collector data (e.g., temperature, persona, quantization). A classifier may latch onto these rather than generalizable model identity. Run category/persona analyses and hold-out-negative-model tests later.
- “Unknown model detection” is **not established** by one-versus-rest validation against the same three negative models encountered in training. A later experiment must hold out one negative model entirely during fitting, while continuing to keep validation/test prompt IDs disjoint.
- Repeated responses to the same prompt are correlated. For confidence intervals or statistical tests, bootstrap **prompt IDs**, not individual response rows.
- Version and random seed are saved in the training settings. Keep the raw files, prompt CSV, and Git commit used for each reported experiment.
- This first baseline uses **response text only** even though the runtime system observes both prompt and response. Adding prompt-conditioned style features is a valid future experiment, not part of the initial comparison.


---

## 9. NEW: Train the remaining three detectors and compare all negative models

The original `train_baselines.py` **already saved separate prediction files for both models**. There is *not* a file literally named `validation_predictions.csv` in the original version. For Gemini 3.1 Pro, the files are:

```text
collector/data/supervised_results/gemini-3.1-pro/all_personas/
├── rf_stylometry_validation_predictions.csv
├── lr_tfidf_validation_predictions.csv
├── rf_stylometry_validation_by_group.csv
├── lr_tfidf_validation_by_group.csv
└── validation_metrics.csv
```

The `*_validation_by_group.csv` reports already contain `group_by=negative_model`, but the new comparison utility gives a fuller breakdown of **which alternative models are incorrectly accepted as the target**.

### A. One command to train the *other three* models

Assuming your four-model data is already consolidated in `collector/data/supervised/`, and your Gemini 3.1 Pro results remain in `collector/data/supervised_results/`, run this from the project root:

```powershell
python scripts/train_all_targets.py --exclude gemini-3.1-pro
```

This trains RF and LR for `gemini-3.8-flash`, `llama3.1-8b`, and `llama3.2-3b` and **reuses** Gemini Pro's existing saved predictions to produce comparisons for all four targets. It discovers exact names from `collector/data/supervised/summary.json` rather than relying on a hard-coded four-model list. It does not train four-way classification: for each target, labels are **1 only for that target, 0 for all others**.

Other useful variants:

```powershell
# Train any target whose complete outputs don't already exist:
python scripts/train_all_targets.py

# Train exactly two named targets:
python scripts/train_all_targets.py --targets llama3.1-8b llama3.2-3b

# Force retraining after data recollection or changed experiment settings:
python scripts/train_all_targets.py --force
```

**Important:** On default settings, a model with complete prior outputs will be reused, not retrained. The script checks training row counts, split prompt counts and the negative model list before reusing it. For changes in dataset composition or hyperparameters, archive the earlier results and retrain with `--force`.

### B. Rebuild the comparison reports at any time *without fitting models*

```powershell
python scripts/summarize_validation.py --require-all
```

This reads existing validation predictions, not the test data. It checks that their record IDs and labels match the current consolidated validation split.

Outputs are in `collector/data/supervised_results/comparison/`:

| Filename | Contents |
|---|---|
| `overall_validation_metrics.csv` | Every target, algorithm and threshold rule, with ROC-AUC, balanced accuracy, recall, change detection and false alarms |
| `negative_model_rates.csv` | For **each alternative model**, the number correctly rejected, incorrectly accepted, false acceptance rate and change detection rate |
| `negative_acceptance_matrix.csv` | Target models as rows; actual alternative models as columns; fraction mistakenly accepted as the row target |
| `baseline_false_alarm_rates.csv` | How often each detector incorrectly rejects its own genuine target responses |
| `all_validation_predictions.csv` | Combined detailed per-response scores and predictions for all models, algorithms and both thresholds |
| `report_manifest.json` | Sources, missing outputs and exact metric definitions |

**Example interpretation:** If `target_model=gemini-3.1-pro` and `negative_model=llama3.2-3b`, then `false_acceptance_rate=0.20` means that **20% of genuine Llama 3.2 3B responses were incorrectly accepted as Gemini Pro**, at that threshold. The corresponding `change_detection_rate` would be `0.80`.

The reports include two threshold policies: `fixed_0.5` and `validation_false_alarm_limit`. The latter is selected to limit false alarms on genuine target-model responses to roughly 10% of validation examples; it is **not** guaranteed to maintain that rate on unseen data. Compare target recall (how often genuine target-model responses are accepted) alongside negative rejection rates.

### C. Methodology notes

- This runs on the **existing development and validation splits**. The final test set stays untouched. Do not select thresholds or classifiers based on test scores.
- Although a validation file contains multiple responses per prompt, these are correlated observations. Avoid interpreting every response as an independent trial. For confidence intervals, resample prompt IDs.
- Negative-model rates are computed on models **included during training**. They do not establish unknown-model change detection. We can test that separately by withholding an entire negative model during fitting and threshold selection.
- If you later add the other three planned LLMs, rebuild consolidation and explicitly retrain. This runner refuses to silently mix stale validation records with the updated dataset.
