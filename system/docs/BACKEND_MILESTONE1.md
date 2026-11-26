# Backend Milestone 1 — FastAPI offline prompt-first prototype

**Status:** Implemented and offline-tested on November 18, 2026. **Not production-ready.**

## Purpose and exact boundaries

This backend is a **small synchronous HTTP prototype**. It proves that a UI can submit **one prompt**, the backend can query a target using the existing `CallableTargetClient`, and our real `PromptAnalysisService` can request the **six versioned Harness probes** and return the fingerprinting result as JSON.

- The **target provider is mocked** and always returns synthetic text.
- The **Harness judge is mocked** (using its real adapter and exact v1 probe questions). It never accepts any model identity.
- **No LoRA weights are loaded, no RF inference is executed, and no real provider/judge API requests occur.** This does not measure LLM identification accuracy.
- There are **no user accounts, API-key inputs, model-card lookups, historical baselines, persistent storage or background workers** in M1.
- Stage 1 stays disabled. If `use_stage1: true` is sent, the API responds with **409 Conflict** because there is no saved confirmed baseline.
- Do not deploy or bind this mock backend to a public network.

## Files in this milestone

| Location | Responsibility |
|---|---|
| `backend/app.py` | FastAPI app factory, routes, sanitized validation errors |
| `backend/schemas.py` | Strict Pydantic request and result contracts; unknown fields rejected |
| `backend/dependencies.py` | Obtain injected analysis service; allows mock swapping in tests |
| `backend/services/analysis.py` | Connect actual prompt workflow, six Harness v1 probes, mock judge |
| `backend/providers/mock.py` | Offline synthetic target replies; no credentials or network |
| `backend/__init__.py`, `backend/services/__init__.py`, `backend/providers/__init__.py` | Python package markers |
| `tests/test_backend_api.py` | HTTP integration, six probes, validation, error/redaction tests |
| `requirements-backend.txt` | FastAPI, uvicorn and httpx dependencies |
| `docs/BACKEND_MILESTONE1.md` | This guide; usage and implementation boundary |
| `TBD.md` | Real-key, provider, worker, auth, history, cards, ML acceptance follow-ups |

## Install and run from your GitHub repository root

Requires Python 3.10+ (use the same virtual environment as your system code).

```bash
python -m pip install -r system/requirements-integrated.txt
python -m pip install -r system/requirements-backend.txt
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000/docs** to inspect the generated OpenAPI documentation and execute a request interactively.

Or use `curl` from another terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"prompt_text":"Explain recursion in Python."}'
```

The response has `mode: "mock"`, a generated `request_id`, `status: "needs_review"`, `model_id: null`, `stage1_enabled: false`, `model_card_status: "unconfirmed"`, `change_status: "no_baseline"`, the list of seven `target_queries`, and the complete nested `report` from `PromptAnalysisService`. **Do not display this as a genuine model prediction.**

```bash
# Health and capability discovery
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/capabilities

# Run new and existing tests from the repository root
python system/run.py test
# Or run only this milestone's HTTP tests:
python -m unittest discover -s tests/core -t . -p test_backend_api.py -v
```

## API contracts (the only implemented endpoints)

| Method | Route | Description |
|---|---|---|
| GET | `/health` | `{ "status": "ok", "mode": "mock" }` |
| GET | `/api/v1/capabilities` | Explicitly says live providers, API keys, baseline history and verified cards are unavailable |
| POST | `/api/v1/analyze` | Synchronous one-prompt mock analysis; HTTP 200 after completion |
| GET | `/docs` | Generated interactive OpenAPI UI |
| GET | `/openapi.json` | API schema for UI integration |

`POST /api/v1/analyze` accepts only:

```json
{
  "prompt_text": "Explain recursion.",
  "use_stage1": false
}
```

The optional `use_stage1` default is `false`. It currently yields HTTP 409 if true. Missing, whitespace-only, non-string, >8000-character, or unrecognized fields yield HTTP 422. Invalid field values are **not echoed** in validation JSON, including an accidentally supplied `api_key`.

A running mock returns **no accepted model card or change claims**. Once we have a real model and an authoritative baseline, the same Python workflow can fill those fields.

## What actually happens for an analysis

```text
Browser / TestClient
       |
       v
POST /api/v1/analyze (prompt only)
       |
       v
backend/app.py  [Pydantic validation]
       |
       v
backend/services/analysis.py  [new request ID]
       |
       v
PromptAnalysisService (existing code)
       |
       +--> CallableTargetClient --> MockTargetProvider (initial prompt)
       |
       +--> Stage 2 SingleMethodStrategy --> HarnessIdentifier
                     |
                     +--> 6 exact prompts from harness/v1 (mock target)
                     +--> injected mock judge -> Unknown
       |
       v
report.to_dict() -> typed JSON response
```

This deliberately exercises our existing workflow and probe-routing code, not a reimplementation of fingerprinting in FastAPI.

## Design decision: one API-key input

For M2/M3 we can offer **one field** for a user-supplied provider key per analysis, and later optionally support "save this key" under authenticated personalization. The backend must also know the provider and its approved model/deployment routing metadata: **a key alone does not tell us which API to call**.

Do not send an API key to the current M1 endpoint (it rejects the field). Future real-key flow requires TLS, authentication, no request-body logging, scope/ownership checks, provider allowlisting, secure worker handoff and consent for external judge calls. For a one-off key, keep it only as long as needed for the authorized analysis; for saved keys, use encrypted storage/secret manager, not a plaintext database field. Both cases still need a server-side judge service credential if the Harness uses a separate judge.

## Next milestones

1. **M2: provider adapter and local-only integration tests.** Define `TargetProvider` interface, support one vetted provider and explicit model selection, apply request timeouts/budgets and simulate API failures. Run live calls only in separately authorized opt-in tests.
2. **M3: credentials, accounts, job lifecycle.** Build authenticated one-off key submission and optionally secure personalization storage; adopt a durable queue/worker and persistent jobs. Do not use long-lived synchronous HTTP calls for six probes + judge + GPU.
3. **M4: saved baselines, cards, and verified results.** Authoritative card resolver, per-deployment confirmed history, change comparison, ML readiness and unknown-model acceptance calibration; adopt `/api/v1/fingerprint/jobs` asynchronous endpoints for the UI.

See `system/TBD.md` for all model-validation and deployment blockers.
