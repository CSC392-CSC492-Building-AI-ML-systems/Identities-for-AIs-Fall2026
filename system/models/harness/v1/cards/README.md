# Domain cards (compliance, governance, evaluation, risk)

After Step 2 identifies a model, these cards tell the user what that model means for the bank: its licence and usage rules (compliance), how it is approved and kept under review (governance), what was measured about it (evaluation), and its known risks (risk).

Every value has a source link and a retrieval date. Missing information is recorded as missing ("Not disclosed"), never guessed.

## What's in this folder

| File | What it is |
|---|---|
| `fields/<domain>.yaml` | The fields of each card: what each one means, where to look for open and closed models, and what to write if nothing is found. |
| `data/<domain>/<model_key>.yaml` | One card for one model. This is what you add or edit. |
| `new_model.py` | Creates blank cards for a new model, with a "where to look" hint above every field. |
| `check_cards.py` | Checks all cards and prints which models and domains are done. Run it before every commit. |
| `show_card.py` | Prints a model's cards, or `--json` for the website and identifier. |
| `cardlib.py` | Shared code; `build_card()` is what other code imports. |

The licence details (conditions, restrictions, bank note) are not repeated here. Each compliance card has a `licence_id` that points to `collector/licences.yaml`, so a licence is summarized once and reused.

## Who fills what

Each field has a `filled_by`:

- **research**: we look it up once per model and store it in `data/`.
- **licence_library**: taken from `collector/licences.yaml`.
- **organization**: entered by the bank when it registers a deployment (e.g. accountable owner, approval decision). Not stored here; the card shows a placeholder.
- **system**: produced by our identifier at run time (e.g. monitoring status, confidence). Not stored here.

Each field also has a `level`. **Family** fields stay true when only the family is known, so they can still be shown when the identifier answers "Unknown" for the version (labelled "not confirmed").

## Setup

Uses the collector's venv (it already has PyYAML). From inside `cards/`:
```
source ../collector/.venv/bin/activate
python check_cards.py
```

## See a card

```
python show_card.py llama3.1-8b                    # all four cards
python show_card.py llama3.1-8b --domain risk      # one card
python show_card.py --family Qwen                  # version unknown: family-level fields only
python show_card.py gemma3-4b --json               # JSON for the website / identifier
```

From Python (e.g. the Step 2 identifier or the website backend):
```python
import sys; sys.path.insert(0, "cards")
from cardlib import build_card
card = build_card("qwen3-8b")           # exact model identified
card = build_card(family="Qwen")        # only the family identified
```

## Add a new model

1. Add it to `collector/models.yaml` (and, for the identifier, to `MODELS` in `agent/identify.py`).
2. Create its blank cards:
   ```
   python new_model.py mistral-small-3.2 --name "Mistral Small 3.2" --family Mistral --access open --by YourName
   ```
3. Research each TODO, following the hint above each field. Good starting searches: `"<model>" model card`, `"<model>" system card`, `"<model>" technical report`; for risk also the [Phare leaderboard](https://phare.giskard.ai) and Artificial Analysis.
4. Set `licence_id` in the compliance card. If the licence is new, add an entry to `collector/licences.yaml` first; either way, add the model to that licence's `applies_to`.
5. Run `python check_cards.py --todo` until the model shows `done` in every column.
6. Commit on a branch and open a pull request.

## Update a card

Edit the value and source, set `retrieved_at` to today, and run `python check_cards.py`. Recheck a card when the developer releases a new version, changes its licence or terms, or publishes a deprecation notice (each governance card lists where to watch).

## Rules

- Every research value needs a `source`.
- Write "Not disclosed" (with the page you checked as the source) instead of leaving a field empty.
- Developer-reported results are labelled as such; independent results say who ran them.
- For risk, `evidence` says how much model-specific evidence exists (`high`, `moderate`, `low`, `none`). A gap in evidence is not "low risk".
- Scores from different benchmarks, settings or effort levels are not directly comparable.
