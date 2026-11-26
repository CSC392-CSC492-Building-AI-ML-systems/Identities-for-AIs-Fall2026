> **Implemented M6 update:** Live jobs can now be linked to owner-scoped deployments and return a typed `result.ui_result` for the frontend. Review [BACKEND_MILESTONE6.md](BACKEND_MILESTONE6.md) for the current, implemented contract. Earlier proposed endpoints below may differ from the actual API.

> **Backend M4 update (November 19, 2026):** An authenticated local
> `POST /api/v1/fingerprint/live-jobs` and owner-restricted GET now exist.
> A separate `--kind live` worker uses an encrypted short-lived local
> credential file; queued prompts/results are encrypted in SQLite. The old
> `/api/v1/analyze/live` route is **disabled by default**. This is a local
> development mechanism, not production login/secret management. See
> [`BACKEND_MILESTONE4.md`](BACKEND_MILESTONE4.md) for the authoritative
> implemented endpoint and startup guide. The sections below describe the
> longer-term intended product and previous milestones.

> **Backend M3 update (local mock jobs only):** The proposed `/api/v1/fingerprint/jobs` POST/GET routes now exist for **mock analyses** in a SQLite-backed worker. Live OpenAI target requests remain synchronous; authentication, credential-safe live workers, and confirmed cards/history are still TODO. See [`BACKEND_MILESTONE3.md`](BACKEND_MILESTONE3.md) for the implemented contract.

> **Backend Milestone 2 update:** A local synchronous OpenAI target route and per-analysis key input are implemented at `POST /api/v1/analyze/live` in `backend/app.py`, using `backend/providers/openai.py`. The target queries are real when supplied a working key; the Harness judge is still MOCK, and no confirmed model result/card/history is available. This is intentionally separate from the *proposed* authenticated production `/jobs` API below. See [BACKEND_MILESTONE2.md](BACKEND_MILESTONE2.md).

# Backend handoff — One prompt, authorized target queries, model cards and changes

**Updated November 18, 2026.** The Python inference/workflow system exists in `system/`. **FastAPI now provides `POST /api/v1/analyze` (offline mock), `POST /api/v1/analyze/live` (OpenAI target with user key, MOCK judge), `GET /health`, and `GET /api/v1/capabilities`.** The live target route works at the protocol level but has not been tested with a real key. Authentication/authorization, persistent async jobs, history, and authoritative cards remain unimplemented. See [`BACKEND_MILESTONE2.md`](BACKEND_MILESTONE2.md) for current routes. The job and connection routes proposed below are NOT implemented.

## Ownership boundary

- **Frontend:** submits a user prompt only, referencing a prior secure connection if necessary. No pasted response or fingerprint probes.
- **Backend:** authorizes that connection, resolves provider/endpoint/target deployment, retrieves the user's key securely, sends the initial prompt, queries any Harness probes, runs the pipeline, resolves cards, loads previous confirmed snapshots, computes changes and returns a sanitized job result.
- **`system/`:** takes a `TargetClient` and user prompt; produces a `PromptAnalysisReport` with the input query IDs, `PipelineResult`, optional card and optional change comparison. **No API key or provider SDK is part of this module.**

A user API key by itself cannot select an AI service or target model. Record an authorized, provider-specific deployment configuration (or use a narrowly scoped connection from a provider catalog). `provider_model_id` may be required for the network call, but **must not be passed to Stage 2 as ground truth**.

## Existing reusable Python code

```python
from pathlib import Path
from system.fingerprinting.adapters.builders import real_adapter_constructors
from system.fingerprinting.clients import CallableTargetClient
from system.fingerprinting.config import load_pipeline_config
from system.fingerprinting.factory import PipelineFactory
from system.fingerprinting.model_catalog import ModelCatalog
from system.fingerprinting.registry import ArtifactRegistry
from system.fingerprinting.workflow import BaselineSnapshot, PromptAnalysisService

system_root = Path('/absolute/path/to/repo/system')
catalog = ModelCatalog.from_file(system_root / 'catalog/models.json')
registry = ArtifactRegistry(system_root, catalog)
config = load_pipeline_config(system_root / 'config/production.yaml', registry)
factory = PipelineFactory(registry, real_adapter_constructors(), require_ready=True)
pipeline = factory.build(config)  # checks artifact bytes, not runtime inference parity

# All three of the following are PROVIDED BY YOUR BACKEND, not this package:
# - provider_connection: a trusted service-specific SDK session from a user-authorized connection
# - card_resolver: your authoritative model-card lookup object (.resolve(model_id, domain))
# - saved_baseline: previously confirmed identity + the card snapshot, if available

client = CallableTargetClient(provider_connection.send_prompt)
service = PromptAnalysisService(pipeline, catalog, card_resolver=card_resolver)
report = service.analyze(
    'Explain recursion in Python.', client, request_id='job-123',
    deployment_id='authorized-deployment-123',
    baseline=BaselineSnapshot('llama3.1-8b', previous_card_snapshot),
    domain='risk', use_stage1=False,
)
result_for_ui = report.to_dict()
```

`provider_connection.send_prompt(text)` is a **backend-supplied callable** that returns a nonempty string, and must use the **same authorized target model/deployment** for both the initial prompt and every Harness probe. Alternatively implement the existing `TargetClient.ask(ProbeQuestion) -> Observation` protocol to retain tokens and latency metadata. The backend obtains credentials via a vault/session; never pass a key as a `PromptAnalysisService` argument or include it in results.

### Runtime sequence

1. Validate auth, connection ownership, provider type, accepted endpoint and quotas. Load a previous confirmed baseline for that deployment if available.
2. Queue a job with `prompt_text`, authenticated connection ID, intended artifact versions and `use_stage1` (false by default). **Do not persist raw API secrets.**
3. Worker constructs `CallableTargetClient` or provider-specific `TargetClient` using a securely retrieved user secret. `PromptAnalysisService` calls `client.ask(ProbeQuestion('UI-INITIAL', prompt))` once to obtain the response/metadata.
4. Stage 1 runs **only** when enabled, and needs a previously known/expected model. Otherwise the Stage 2 fallback executes LoRA on the initial reply, then automatically asks the six Harness probes if it reaches Harness, followed by Random Forest if needed. The backend does not need to pre-collect every probe; `FallbackStrategy` asks them on demand and caches each by ID within that execution.
5. If a model identity was **accepted**, resolve its canonical model card using the backend's card service. If no card exists, return `model_card_status='unavailable'`, not invented data.
6. If a previous *confirmed* baseline exists, compare current accepted ID against it. If both old and new domain-card snapshots exist and have compatible schemas, compute field changes; otherwise return `card_comparison_status='not_comparable'`.
7. Return a sanitized, versioned result; update per-deployment history **only under a documented acceptance policy**. A `review_only` candidate is not a confirmed model baseline.

## Suggested production HTTP endpoints (NOT YET IMPLEMENTED; distinct from M1 mock routes)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/connections` | Establish a secure provider connection (or OAuth); do not save plaintext keys in the application database |
| `GET /api/v1/connections` | List only the authenticated user's available target connections, not secrets |
| `POST /api/v1/fingerprint/jobs` | Accept `prompt_text`, authorized `connection_id`/session, `use_stage1=false` and optional `domain`; return `202` with job ID |
| `GET /api/v1/fingerprint/jobs/{id}` | Return queued/running/completed/error status and results the user is authorized to view |
| `POST /api/v1/fingerprint/jobs/{id}/cancel` | Best-effort cancellation to stop further provider/judge spending |
| `GET /api/v1/models/{canonical_id}/card` | Source-aware card lookup (scope and access enforcement required) |
| `GET /api/v1/connections/{id}/history` | Return confirmed baseline snapshots/changes without secrets |
| `GET /api/v1/fingerprint/capabilities` | Expose supported IDs, methods, availability, optional Stage 1, and known limitations |

Never accept arbitrary unvalidated network URLs for `TargetClient` from a web request: restrict to vetted provider hosts to prevent SSRF. Protect against prompt injection in judge results, set budgets for at most the requested initial prompt + configured probes, rate-limit by user/deployment, and avoid sending user prompt/response data to additional judge providers without explicit permission.

## What current `system/` can actually guarantee

- `models/lora/v2` contains the newly supplied **Qwen2.5-0.5B rank16 alpha32** weights, five-output score head and matching hashes. Its label order is provisional and Hugging Face base revision is **`main` (not pinned)**. Its **real inference has not been executed** here; `peft`/`transformers` are separate dependencies. LoRA v2 intentionally returns only unlabeled class scores until its class mapping is verified; it cannot accept a model identity until unknown-model rejection is also validated.
- `harness/v1` contains six versioned probes and offline dependencies. A real judge call requires explicit provider setup and consent; mock judge is **not identification evidence**.
- `random_forest/v1` is checksummed but review-only and uses prompt/serving metadata that may shift. Stage 1 only supports four target IDs and is opt-in.
- The Factory's `--require-ready` checks bytes/hashes but **not** provider credentials, HF base checkpoint availability, class-label parity, calibration, cards or live end-to-end reliability.
- `PromptAnalysisService` is **synchronous Python orchestration**, not a queued HTTP job. The backend must add asynchronous execution, cancellation, progress, retry semantics, timeouts, metrics, privacy controls and appropriate resource isolation (GPU for LoRA, judge API for Harness).

## Security and data handling

- API secrets in a managed secret vault or short-lived server memory only. Never commit, include in model telemetry, return to browser, or log key material. Consider direct provider OAuth where available; if user keys must be submitted, use a separate TLS-protected setup endpoint.
- Restrict connection ownership, deployment hostnames and supported providers; validate auth on every job/status/card request. Keep target-model routing identifiers out of classifier features except explicitly documented prompts/response and measurements.
- Do not copy private target response text into telemetry, browser diagnostics, public datasets or logs by default. Define user consent and retention policies, including sharing with an external Harness judge.
- Version/pin base models and classifier artifacts, surface partial failures, cap API spend, and keep outcome states (`identified`, `verified`, `drift_detected`, `needs_review`, `error`) distinct.

**Development checkpoints:** use `python system/run.py example prompt_workflow_mock_demo` for offline contract testing, then run the M2 OpenAI target against a controlled development deployment; implement authenticated jobs and a card resolver before public use. Real judge and full E2E accuracy require separate validation. Track all remaining work in `system/TBD.md`.
