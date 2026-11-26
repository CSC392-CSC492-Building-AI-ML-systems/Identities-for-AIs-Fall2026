> **M6 supersedes the live-job linkage limitation below.** The latest linked jobs and typed UI results are documented in [BACKEND_MILESTONE6.md](BACKEND_MILESTONE6.md). M5 reviewed-baseline creation and card lookup remain as described here.

# Backend Milestone 5 — Real repository cards and reviewed model history

This milestone adds **read-only access to the team's authoritative `cards/` library** and **owner-scoped, persistent history for manually reviewed deployment identities**. It extends the M4 FastAPI backend without replacing the M4 worker, queue, or credential safeguards. It does **not** validate the fingerprint classifiers, implement a real Harness judge, or automatically promote ML predictions to confirmed baselines.

## Directory contract

At the GitHub root, the project should contain sibling folders:

```
Identities-for-AIs-Fall2026/
  cards/
    cardlib.py
    fields/...
    data/{compliance,governance,evaluation,risk}/...
  collector/
    licences.yaml
  system/
    backend/
      cards_repository.py       # read only, uses sibling cards/cardlib.py
      history_api.py            # FastAPI endpoints
      history_schemas.py        # strict request validation
      history_store.py          # owner-scoped SQLite baselines
    docs/BACKEND_MILESTONE5.md
    CLEANUP_REVIEW.md          # proposed removals, all unapproved
```

**Do not copy `cards/data/` into `system/` for M5.** `cards/cardlib.py` already generates all four domains and resolves licence information from `collector/licences.yaml`. M5 reuses it. If `cards/` is not installed alongside `system/`, card endpoints will report `unavailable`, never manufacture card contents. The Harness v1 artifact has a separate pinned historical snapshot; do not delete or repoint it without publishing a new verified artifact.

## HTTP API (development only)

All M5 endpoints require the M4 local bearer token and return 401 without it. Deployments and history are scoped to the bearer token's owner; another user's ID returns 404 rather than revealing whether a record exists.

| Endpoint | Action |
|---|---|
| `GET /api/v1/models/{model_id}/card` | Read the exact model's public card from sibling `cards/`, or `unavailable` |
| `POST /api/v1/deployments` | Register a monitored provider routing identifier (not an inferred model) |
| `GET /api/v1/deployments` | List only the authenticated owner's deployments |
| `GET /api/v1/deployments/{id}` | Get one deployment and its latest reviewed baseline |
| `POST /api/v1/deployments/{id}/baselines` | Explicitly append a **manually reviewed** baseline + immutable card snapshot |
| `GET /api/v1/deployments/{id}/history` | Fetch full baseline revision history and saved card snapshots |
| `GET /api/v1/deployments/{id}/changes` | Compare last two reviewed baselines, including field values/sources and family change |

### Walkthrough using Swagger on Windows Git Bash

From the **repository root**, with Python 3.11+ and the existing `.venv`:

```bash
source .venv/Scripts/activate
python -m pip install -r system/requirements-backend.txt
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/docs`. Use **Authorize** and enter your M4 locally provisioned bearer token, not your OpenAI API key. Then:

1. `GET /api/v1/models/llama3.1-8b/card`: expect four real card domains when sibling `cards/` exists.
2. `POST /api/v1/deployments` with:
   ```json
   {"label":"Research deployment A","provider":"openai","requested_model_id":"my-existing-alias"}
   ```
   `requested_model_id` is the **routing identifier**, not a predicted model. Record the returned `id`.
3. After a person has **independently reviewed evidence** about the underlying model, use `POST /api/v1/deployments/{id}/baselines`:
   ```json
   {
     "model_id":"llama3.1-8b",
     "acknowledge_manual_review":true,
     "review_note":"Reviewed deployment evidence and confirmed by a human"
   }
   ```
4. For a subsequent independently reviewed model identity, add a second revision, e.g. `llama3.2-3b` with a new review note.
5. `GET /api/v1/deployments/{id}/changes`: returns `identity_change`, `family_change`, and changed card fields. `GET /history` retains previous full snapshots even when current card YAML is subsequently updated.

### How to interpret results

* The card library's `confirmed: true` means **an exact-model card**, not proof that a particular deployment is that model.
* A human submitting a baseline declares `confirmation_source: manual_review`; this is an **operator assertion**, not a verified ML result. Store an evidence note, not a raw API key or private prompt.
* Only catalog-supported IDs can be recorded as reviewed baselines in M5. Unknown seventh families remain `needs_review` until onboarding and validated open-set detection exist.
* No baselines are added automatically from mock, review-only LoRA/RF candidates, or a mock Harness judge.
* A change in stored identity or card content describes the **two manual-review snapshots**; it is not definitive evidence of provider-side substitution.
* When no prior snapshot or no card is available, the API reports `no_previous_baseline` or `card_unavailable` instead of fabricating a change.
* The response's `family_change` is derived from the canonical `system/catalog/models.json`, not from strings inferred from the card data.
* Organization/system fields in team cards are template placeholders. They do not imply an actual organization's approvals, audits or monitoring state.

### Privacy and deployment limits

This is a **local-development**, M4-token authenticated prototype. SQLite stores card snapshots, deployment labels, routing IDs and reviewer notes **in plaintext**, which may remain in WAL files and backups. Do not use confidential notes or publish `system/.local/`. It needs production login/OIDC, encryption at rest, data retention policies, rate limits, HTTPS and a managed database before multi-user deployment. The API does not store provider credentials in M5 tables. The existing M4 encrypted live-job storage is unchanged.

### Not yet wired to live analysis jobs

The M4 live job still runs with a mock Harness judge. M5 does not auto-associate those jobs with a deployment or turn a candidate prediction into a baseline. A future step will add owner-checked deployment-to-job association and a **read-only** comparison for accepted, validated identities. Stage 1 opt-in also needs that authorized baseline supplied to the worker, with support checks for expected model IDs. This is on `system/TBD.md`.

## Testing

```bash
python -m unittest system.tests.test_backend_history -v
python -m unittest system.tests.test_backend_api system.tests.test_backend_live_jobs -v
python system/run.py test
```

The M5 tests use synthetic card data, no real provider calls, and two users to verify isolation and immutability. The integration was additionally smoke-tested against your repository's actual `cards/cardlib.py` and YAML files, which return four card domains for `llama3.1-8b` and `qwen3-8b`.
