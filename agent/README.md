# Agentic model identifier (harness approach)

An LLM (Gemini by default) guesses which model wrote a chatbot answer. The harness gives it context: example answers from every known model to the same prompt, taken from our fingerprinting data. It returns family, version, confidences and a reason, and looks up the predicted model's licence (from `collector/licences.yaml`).

## How it's tested

Answers with `sample_index` 0 and 1 are the examples; `sample_index` 2 is the test set, so the LLM is never tested on an answer it was shown. It reports family and version accuracy, accuracy per model, and the most common mistakes, and saves every guess to `results.jsonl`.

## Setup

1. Use the collector's venv (it already has PyYAML): `source ../collector/.venv/bin/activate`
2. Get a free Gemini API key at https://aistudio.google.com and add `GEMINI_API_KEY=...` to `collector/.env` (never commit it).

## Run

```
python identify.py --dry-run --limit 1        # show the context sent to the LLM, call nothing
python identify.py --provider mock --limit 5  # test the pipeline with a fake LLM
python identify.py --limit 20                 # real run on 20 test answers
```

Options: `--model` (default `gemini-3.8-flash`), `--provider` (`google`, `anthropic`, `openai`), `--delay` (seconds between calls, default 4 for the free tier).