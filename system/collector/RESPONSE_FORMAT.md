# Response Record Format

Every model answer the collector (`collect.py`) saves is one **response record**.

Records are stored as **JSON Lines** (`.jsonl`): one record per line.

- New records are appended, so an interrupted run can resume where it stopped.
- Load in Python with `pandas.read_json("file.jsonl", lines=True)`.
- Files are named `data/raw/<model_key>/<prompt_set_version>.jsonl`, e.g. `data/raw/llama3.1-8b/training_v1.jsonl`. When `--tag` is used, the tag is added: `training_v1__noon.jsonl`.

## Fields

| Field | Type | Example | Description |
| --- | --- | --- | --- |
| `record_id` | string (UUID) | `"3f2a9c1e-…"` | Unique ID for this response |
| `collected_at` | string (ISO 8601, UTC) | `"2026-10-14T14:02:11Z"` | When the response was received. Needed for drift detection, which compares responses over time |
| `prompt_set_version` | string | `"training_v1"` | Which prompt set and run this came from (`training_v1`, `training_v1_no_persona`, `fingerprint_v0`, `baseline_v0`). Results from different prompt sets shouldn't be mixed without knowing it |
| `prompt_id` | string | `"WC-021"` | ID of the prompt in its prompt file (`source_id` in the training sheet, `id` in the fingerprint file) |
| `prompt_group` | string | `"wildchat_4.8m"` | Group of the prompt: the `group` column of the training sheet, or `llmmap_original` / `our_probe` / `v1_creative` for fingerprinting |
| `prompt_category` | string or null | `"General Q&A and explanation"` | Task area from the training sheet, so results can be split by category. `null` for fingerprint prompts |
| `persona_id` | string | `"BK2"` | ID of the system prompt in `personas.yaml` (`P13` = no persona) |
| `sample_index` | integer | `0` | Repeat number (0, 1, 2) for the same prompt, persona and model. Keeps repeat samples apart; the classifier needs several per model |
| `run_type` | string | `"library"` | `library` (training data), `baseline` (Step 1 reference for a deployment) or `monitoring` (later checks against that baseline). Keeps the three kinds of data from being mixed up |
| `deployment_id` | string or null | `"bank-support-bot"` | Which simulated deployment a baseline or monitoring run belongs to. `null` for training data |
| `model_key` | string | `"llama3.1-8b"` | Our name for the model, from `models.yaml` |
| `provider` | string | `"ollama"` | Where the model was called (`ollama`, `openai`, `anthropic`, `google`) |
| `requested_model` | string | `"llama3.1:8b"` | Exact model ID sent in the request |
| `served_model` | string or null | `"llama3.1:8b"` | Model ID the provider reports in its response. A mismatch with `requested_model` is evidence of a silent swap (Use Case 2) |
| `temperature` | number | `0.7` | Sampling temperature |
| `max_tokens` | integer | `1200` | Maximum response length requested |
| `response_text` | string or null | `"Here's a summary…"` | The answer, without any reasoning text. `null` when the prompt has `save_response: refusal_only` (e.g. LM-02) |
| `reasoning_text` | string or null | `"Okay, the user wants…"` | "Thinking" text some models output (e.g. Qwen3 inside `<think>…</think>`), kept separate so it doesn't skew style features. `null` if none |
| `refused` | boolean or null | `false` | **Preliminary** refusal flag from a keyword check in the collector; can be relabelled later by the NLP/ML team. Refusal rate goes on the evaluation and risk cards, and LM-02 has no saved text to check later |
| `finish_reason` | string or null | `"stop"` | `"stop"` = completed; `"length"` = cut off at `max_tokens`. Cut-off answers can skew style features, so the NLP team can filter them out |
| `input_tokens` | integer or null | `212` | Tokens sent. For tracking API cost |
| `output_tokens` | integer or null | `148` | Tokens received. For tracking API cost |
| `latency_ms` | integer or null | `1840` | Time from request to full response |
| `error` | string or null | `null` | Error message if the call failed. Failed calls are recorded rather than dropped, so we can see which models or providers fail instead of the data silently thinning out |
| `tag` | string or null | `"noon"` | Label for the round, from `--tag`. Lets a repeat run (e.g. noon vs midnight, for drift) be saved and told apart. `null` if no tag was used |
| `seed` | integer or null | `1000` | Random seed sent to Ollama (1000 + `sample_index`), so an answer can be reproduced. `null` for API models |
| `model_digest` | string or null | `"68ceab7e…"` | Ollama's ID for the exact model file. If it changes between runs, the model was updated or re-pulled, so a difference is not drift. `null` for API models |
| `quantization` | string or null | `"Q4_K_M"` | Compression level of the local model. Confirms everyone ran the same version. `null` for API models |

## Example record

Shown on several lines for readability; in the file it is a single line.

```json
{
  "record_id": "3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90",
  "collected_at": "2026-10-14T14:02:11Z",
  "prompt_set_version": "training_v1",
  "prompt_id": "WC-021",
  "prompt_group": "wildchat_4.8m",
  "prompt_category": "General Q&A and explanation",
  "persona_id": "P15",
  "sample_index": 0,
  "run_type": "library",
  "deployment_id": null,
  "model_key": "llama3.1-8b",
  "provider": "ollama",
  "requested_model": "llama3.1:8b",
  "served_model": "llama3.1:8b",
  "temperature": 0.7,
  "max_tokens": 1200,
  "response_text": "I couldn't find reliable information about a character named Juna Crawford...",
  "reasoning_text": null,
  "refused": false,
  "finish_reason": "stop",
  "input_tokens": 98,
  "output_tokens": 64,
  "latency_ms": 1840,
  "error": null,
  "tag": "noon",
  "seed": 1000,
  "model_digest": "68ceab7e468a31c988b44d5a4984a0e21f58c4f7158c6ce29c1804babac38df7",
  "quantization": "Q4_K_M"
}
}
```

## Rules

- **Never edit a saved record.** Corrections or relabels go in a separate file keyed by `record_id`, so the raw data stays an exact record of what each model returned.
- **No API keys or personal data** in any record. Prompts use made-up names and numbers only.
- **Adding a field** is allowed (older records just lack it). **Renaming or removing a field** requires bumping the version and telling the team.