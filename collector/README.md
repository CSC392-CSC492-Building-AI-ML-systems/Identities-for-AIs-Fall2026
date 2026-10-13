# Data collector

Sends prompts to each model and saves every answer in the same format, so data collected by different people can be combined.

## What's in this folder

| File | What it is |
|---|---|
| `collect.py` | The script. Sends each prompt to each model and saves one record per answer. |
| `models.yaml` | Which models to call (exact IDs). Closed models are off by default; turn one on once its API key is in `.env`. |
| `prompts/training_prompts.csv` | The 300 training prompts (exported from the Stage1 Prompt Collection sheet). |
| `prompts/fingerprint_prompts.yaml` | The 32 fingerprinting prompts (Step 2). |
| `prompts/personas.yaml` | The system prompts (P01–P15, BK1–BK4; P13 = no persona). |
| `RESPONSE_FORMAT.md` | What each saved field means. |
| `licences.yaml` | Licence summaries for each model (used by the compliance card). |
| `.env.example` | Template for API keys. Copy to `.env`. |

## Setup (once)

1. Python 3.9+, then `pip install -r requirements.txt`
2. Install Ollama (https://ollama.com), then pull the open models:
   ```
   ollama pull llama3.1:8b
   ollama pull llama3.2:3b
   ollama pull qwen3:8b
   ollama pull qwen3.5:9b
   ollama pull gemma3:4b
   ```
   Ollama runs at `http://localhost:11434`. These tags are 4-bit quantized versions.
3. Only for closed models: `cp .env.example .env` and add your key. **Never commit `.env`.**

## Run it

```
python collect.py --dry-run --limit 2                # shows what would be sent, calls nothing
python collect.py --model mock-model --limit 3       # tests the whole pipeline without a real model
python collect.py --model llama3.1-8b --limit 1      # first real test: 1 prompt on 1 model
python collect.py --model llama3.1-8b                # full training run for one model
python collect.py                                    # all enabled models
```

No-persona comparison (small subset, everything with P13):
```
python collect.py --subset 3 --persona P13 --prompt-set-version training_v1_no_persona
```
`--subset 3` takes 3 prompts from each category (24 prompts, 72 answers per model). It picks the same prompts every time.
Use a separate `--prompt-set-version` so this data stays in its own file.

Fingerprinting prompts (Step 2), run under several personas:
```
python collect.py --prompts prompts/fingerprint_prompts.yaml --prompt-set-version fingerprint_v0 \
                  --persona P13 --persona BK1 --persona P05
```

Baseline / monitoring run for one simulated deployment (Step 1):
```
python collect.py --prompts <baseline file> --prompt-set-version baseline_v0 \
                  --run-type baseline --deployment-id bank-support-bot --persona BK1 --samples 10
```

**Stopping is safe.** Run the same command again and it skips answers already saved. Failed calls are saved with an `error` and retried on the next run.

## Settings (top of `collect.py`)

**Temperature and max tokens are not final yet.** The defaults are V1's values (from its collect_data.py).
Change them per run with flags. Every record saves the values used, so data from different settings never gets mixed up.

| Setting | Default | Flag |
|---|---|---|
| Samples per prompt | 3, all with the sheet's persona | `--samples` |
| Temperature | 0.7 | `--temperature 0.7`, or repeat the flag to cycle values per sample |
| Max tokens | 1200 | `--max-tokens 1500` |
| Persona | the sheet's `persona_id` | `--persona P13` (repeatable) |
| Subset | all prompts | `--subset N` = N per category |

To check whether max tokens is high enough, count records with `"finish_reason": "length"` (answer cut off). Qwen's thinking text uses tokens too.

Size of a full training run: 300 prompts × 3 samples = **900 answers per model**.

## Output

`data/raw/<model_key>/<prompt_set_version>.jsonl`, one JSON record per answer. The fields are described in `RESPONSE_FORMAT.md`.

`data/` is not committed to git (it gets big).

## Known limitations

- The OpenAI model IDs in `models.yaml` are not set yet.
- Anthropic and Gemini are called through their OpenAI-compatible endpoints. Test each with `--limit 1` before a full run.
- The `refused` flag is a keyword check only, so it can be wrong.