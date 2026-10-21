# Fingerprinting dataset consolidation

This script consolidates the collected raw JSONL records; it does not perform feature engineering or train a Random Forest.

## Expected project layout

```text
project/
├── consolidate_fingerprints.py
├── prompts/
│   └── fingerprinting_prompts.yaml
└── data/
    └── raw/
        ├── <model_1>/fingerprint_v0.jsonl
        ├── <model_2>/fingerprint_v0.jsonl
        ├── <model_3>/fingerprint_v0.jsonl
        ├── <model_4>/fingerprint_v0.jsonl
        ├── <model_5>/fingerprint_v0.jsonl
        └── <model_6>/fingerprint_v0.jsonl
```

## Running it

From the project root:

```bash
python -m pip install pyyaml
python consolidate_fingerprints.py --prompts prompts/fingerprinting_prompts.yaml
```

If you placed the YAML at a different location, change the path passed to `--prompts`.

The script defaults to `--raw-dir data/raw`, `--output-dir data/processed`, `--persona P13`, and `--expected-models 6`.

To change persona:

```bash
python consolidate_fingerprints.py --prompts prompts/fingerprinting_prompts.yaml --persona P12
```

For a **one-model test** (the normal production run expects six):

```bash
python consolidate_fingerprints.py --prompts prompts/fingerprinting_prompts.yaml --expected-models 1
```

For all CLI options:

```bash
python consolidate_fingerprints.py --help
```

## Outputs

In `data/processed/`:

- `fingerprint_v0_all.csv`: all records, every model, every persona.
- `fingerprint_v0_P13.csv`: only records with `persona_id` exactly equal to `P13`.
- `fingerprint_v0_validation.json`: counts by model/persona, missing-response breakdown, duplicate warnings, and source-file inventory.

Both CSVs have **identical columns**. Each JSONL record becomes one CSV row, including repeated generations. The script preserves the original keys/metadata and adds:

| Column | Meaning |
|---|---|
| `prompt` | Original prompt text, joined from the YAML using `prompt_id` |
| `prompt_source` | Prompt source listed in YAML |
| `save_response` | `full` or `refusal_only`, from YAML |
| `source_file` | Source file path relative to `data/raw` |
| `response_is_null` | `true` if `response_text` is JSON null or absent |
| `response_missing` | `true` if `response_text` is null, empty, or whitespace-only |
| `response_missing_expected` | `true` if missing and the YAML says `refusal_only` |

CSV cannot distinguish a JSON `null` from an empty string using the response cell alone, so use the Boolean flags to preserve that distinction. Null responses are not replaced with invented text or removed. In the provided YAML, `LM-02` intentionally has `save_response: refusal_only`.

The script refuses to generate exports if prompt IDs cannot be matched to the YAML or if the distinct model count differs from `--expected-models`. It reports (but does **not** automatically delete) repeated record IDs or repeated model/prompt/persona/sample keys. All original raw files remain unchanged. Running it again updates only the files under the output directory.

**For later machine learning:** `model_key` is the target label. The presence of `model_key`, `provider`, or `served_model` as metadata in the CSV does **not** mean they should be used as input features. You can select `prompt_id`, text-derived features from `prompt`/`response_text`, `output_tokens`, and `latency_ms` in a separate feature-extraction script. Use held-out generations when comparing classifiers for your fixed-prompt identification task.

## Verification performed

The script was tested against the uploaded `llama3.1-8b` JSONL file and a separate synthetic six-model test. The real single-model test retained 768 total records and 96 `P13` records; 24 records had intentionally omitted response text, including three in `P13`.
