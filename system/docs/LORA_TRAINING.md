# Automated LoRA training — prototype

Implemented from `research/team_sources/lora/v2_lora_finetuning.ipynb`, whose source cells match the original teammate archive (original notebook SHA-256 `7225592f149db7fdaa00324aa4e41ab5839262bee2d10dd68eb8cb7b3a5c42e1`). No new real checkpoint is shipped. This environment has CPU-only PyTorch and lacks Transformers, PEFT and Accelerate; actual fine-tuning and real inference reload remain untested.

## Recipe and adaptations

- Qwen2.5-1.5B sequence classification, rank 32, alpha 64, dropout 0.05, seven projection targets, 512 tokens, 8 epochs, LR 1e-4, weight decay 0.01, batch size 2, accumulation 8, seed 42. Optional 0.5B base for lower memory; default training cap 200 rows/class.
- The notebook warns not to mix models answering different questions. Balance every retained `(prompt_set_version, prompt_id)` cell across all selected model classes using deterministic sampling; report discarded rows. The notebook calculated class weights but did not use them in Trainer. Balanced quotas use ordinary cross-entropy. Its TF-IDF baseline is not ported here.
- Consume verified train/validation exports only. Both unseen-prompt and fixed-panel persona splits are supported with shared prompt coverage checks. For panel, personas are disjoint and shared prompts match. No calibration/test data used for fitting. Validation reports the balanced subset, not all source rows if filtering occurs.
- Blank no-error responses are encoded as `[EMPTY_RESPONSE]`; literal marker and leading backslash are escaped. Ordinary response text is stripped. Shared `lora_preprocessing.py` applies the same rule at inference. Historical checkpoints use their original strip-only policy. No prompt, label, persona, routing metadata or reasoning field is passed to the model. Blanks are not necessarily intentional refusals.
- Sorted canonical class IDs used in training and persisted with the trained score head; base and tokenizer loaded at the same pinned commit. Review-only candidate, never auto-activated.

## Preview actual data

```bash
python system/tools/preview_lora_training.py --config system/config/training/lora_candidate.json
```

The shipped `reports/lora_candidate_data_preview.json` uses the Agentic snapshot and `rf_panel_v1`: 1,224 train / 306 validation responses, 72 / 18 per class across all 17 classes, 42 / 17 blanks, zero rows discarded. Four train personas and one validation persona. Same six probes across partitions. LoRA uses single responses, not RF's combined traces. Fixed known-probe performance cannot establish generalization to arbitrary user prompts; collect a wider balanced cohort. Historical reference overlap is unresolved. Neither preview nor training reads test responses for model fitting or selection.

## Run on a GPU

Use a separate Python 3.11+ environment. Install an appropriate CUDA PyTorch build for your hardware; do not downgrade the integrated RF environment to sklearn 1.6.1. Freeze resolved versions after a real smoke test.

```bash
python -m venv .venv-lora
source .venv-lora/Scripts/activate  # Windows Git Bash; Linux: source .venv-lora/bin/activate
python -m pip install -r system/requirements-lora-training.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Copy `system/config/training/lora_candidate.json` to `system/config/training/lora_candidate_local.json`. Replace `REPLACE_WITH_EXACT_40_CHARACTER_COMMIT` with the real Hugging Face commit of the selected base. The notebook did not record this; none is invented. Use a new artifact ID. The plan is metadata-only: it refuses an unpinned base but does not check remote commit existence, installed dependencies or GPU memory.

```bash
python system/run.py training methods
python system/run.py training plan --config config/training/lora_candidate_local.json
python system/run.py training run --config config/training/lora_candidate_local.json \
  --method lora --approve-dataset --register-candidates
```

`run.py` resolves config paths relative to `system/`. A 1.5B model can exceed available GPU memory. For a smoke run use 0.5B with its own pinned commit, 1 epoch, smaller max_tokens, batch size 1, small cap at least one row per shared prompt, distinct smoke artifact ID, and omit `--register-candidates`. CPU requires device `cpu` and precision `fp32`; CPU training is slow. `local_files_only: true` uses cached files. No automatic device fallback or retry. `model_ids` optionally selects a subset of classes occurring in both partitions. `max_train_per_class: null` uses all balanced rows.

## Outputs and evaluation

The orchestrator keeps plan/result, candidate files and local trainer work in `.local/training_runs/<id>/`. Bundle: `adapter_model.safetensors`, `adapter_config.json`, `data_report.json`, `validation_report.json`, `manifest.json`. Includes hashes, training code revision, dependency versions, label order, trained head shape, split provenance and training parameters. Validation includes exact accuracy, macro-F1, confusion matrix and classification report. Registration uses existing onboarding; structural validation is not real runtime certification. Unsuccessful runs are not registered. Inspect/delete interrupted local runs only after they are inactive.

After training, freeze the candidate, create a candidate config and run the separate evaluator:

```bash
python system/run.py onboard-classifier candidate-config lora/v3 --single --output config/experiments/lora_v3_candidate.yaml
python system/tools/evaluate_lora_split.py --config system/config/experiments/lora_v3_candidate.yaml --output local_lora_test.json
```

The evaluator uses the existing Factory and EvaluationRunner on the pinned test partition. It reports balanced single-response exact/family accuracy, not multi-query trace-level accuracy or open-set performance. Actual reload, validation prediction parity, and real test performance remain to be checked. No thresholds selected. Live HTTP worker still uses mock Harness, so registration does not switch frontend inference. No previous artifacts/config/raw data changed or deleted.

## Tests

```bash
python -B -m unittest tests.core.test_lora_training tests.core.test_lora_adapter.LoRAAdapterTests tests.core.test_lora_v2_bundle -v
```

Synthetic fixture weights and predictor verify export, onboarding and evaluator contracts only. No GPU training results are claimed.
