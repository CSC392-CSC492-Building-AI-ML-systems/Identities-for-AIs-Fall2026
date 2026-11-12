# LoRA Fine-Tuning

The goal is to see whether a small open-weight model, fine-tuned with LoRA, can look at a chatbot answer and say which model wrote it. 
Our mentor said that a few hundred records is enough for fine-tuning, and that the point is to get experience with the process even if the results are weak.

### Methodology & Configuration
* **Base Model:** `Qwen/Qwen2.5-1.5B` (sequence classification head)
* **Task:** 5-class text classification (`gemma3-4b`, `llama3.1-8b`, `llama3.2-3b`, `qwen3-8b`, `qwen3.5-9b`). *(Note: the notebook also supports a separate 2-class `"gemini"` bonus run, which must never be mixed with `"open_models"` due to differing prompt sets.)*
* **LoRA Settings:** Rank `32`, alpha `64`, dropout `0.05`, applied across attention and feed-forward projection layers (`q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`).
* **Training Hyperparameters:** `8` epochs, learning rate `1e-4`, weight decay `0.01`, fp16 precision, per-device batch size `2` with `8` gradient accumulation steps (effective batch size `16`), max sequence length `512` tokens.
* **Data Split & Leakage Prevention:** Split by `prompt_id` (roughly 20% of prompts per group held out for testing) rather than by individual records. Because each prompt was queried multiple times, splitting by question prevents near-duplicate answers from leaking across train and test sets.
* **Dataset Size & Balance:** `3,087` usable records filtered from `3,840` raw records. Training set is capped at `200` examples per class (`898` total; `98` available for `qwen3.5-9b`), evaluated on `697` test examples.
* **Baseline:** TF-IDF (1–2 n-grams) + Logistic Regression trained and evaluated on the exact same split.

### Current Results (`open_models`)
* **Random Guessing:** `0.200`
* **TF-IDF Baseline:** `0.631` exact model | `0.819` model family
* **LoRA (`Qwen2.5-1.5B`):** `0.676` exact model | `0.894` model family

### Key Files
* `lora_llm_identification.ipynb`: End-to-end Colab notebook covering data filtering, question-grouped splitting, TF-IDF baseline, LoRA training, evaluation, and inference.
* `my_lora_adapter.zip` (unpacks `adapter_model.safetensors` and `adapter_config.json`): Saved PEFT adapter weights exported from Step 10.

### How to Reproduce (Training in Colab)
1. Open `lora_llm_identification.ipynb` in Google Colab and select a **T4 GPU** runtime (`Runtime > Change runtime type > T4 GPU`).
2. Run Steps 1–2 to verify GPU allocation and install `peft`, `accelerate`, and `transformers`.
3. Run Step 3 and upload the five open-model fingerprinting `.jsonl` files (`*fingerprinting*`).
4. Run Steps 4–5 to prepare the train/test split and compute the TF-IDF baseline.
5. In Step 6, run `!pip uninstall -y -q torchao`, restart the runtime session if prompted, and re-run Steps 4–6 to avoid `torchao` conflicts with PEFT.
6. Run Steps 7–10 to tokenize the data, train for 8 epochs (~35 minutes on a T4), evaluate on the held-out test prompts, and download `my_lora_adapter.zip`.

### Integration / Inference Notes (For E2E Testing)
To run inference without retraining, load `Qwen/Qwen2.5-1.5B` via `AutoModelForSequenceClassification` (`num_labels=5`) and attach the unzipped adapter folder using `peft`:
* **Label Order (`id2label`):** `0: gemma3-4b`, `1: llama3.1-8b`, `2: llama3.2-3b`, `3: qwen3-8b`, `4: qwen3.5-9b`.
* **Preprocessing:** Strip whitespace and tokenize with `truncation=True` and `max_length=512` (using `eos_token` as `pad_token` with right padding).
* **Output:** Apply `softmax` over output logits to obtain per-class probabilities (see `which_model(text)` in Step 10).
