## Backend Milestone 3 — durable mock jobs (NEW)

The FastAPI backend now supports `POST /api/v1/fingerprint/jobs` (returns a
queued **mock** job ID immediately) and `GET /api/v1/fingerprint/jobs/{job_id}`
(poll state/result). A **separate SQLite worker process** runs the existing
prompt-first mock workflow. Job states persist across API restarts; no real
provider credentials are accepted or queued. The synchronous OpenAI-target
endpoint from M2 remains available for local, opt-in testing with a mocked
judge. See [docs/BACKEND_MILESTONE3.md](docs/BACKEND_MILESTONE3.md).

Run the server and worker in two Windows Git Bash terminals from the repo root:

```bash
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
# separate terminal, same venv:
python -m system.backend.worker --loop --poll-seconds 1
```

**Security:** mock job inputs temporarily store prompts in an unencrypted
local SQLite file (`system/.local/jobs.sqlite3`, gitignored). No auth exists.
Do not expose this backend publicly or submit secrets or private prompts.

## Backend Milestone 2 — local OpenAI target route

In addition to the existing offline mock route (`POST /api/v1/analyze`), the FastAPI backend now provides an opt-in **live OpenAI target** route (`POST /api/v1/analyze/live`). A user-supplied key is used for a single synchronous analysis, including the real target's initial response and, if reached, six Harness prompts. The judge is still **mocked** and identities must remain **unconfirmed**. No real provider test using paid credentials has been run. See [docs/BACKEND_MILESTONE2.md](docs/BACKEND_MILESTONE2.md) and [`backend/README.md`](backend/README.md).

The UI analysis screen remains **prompt-only**: the target API key and provider/model routing fields are entered in connection settings or in a separate local development form. No credentials are persisted yet.

# LLM Fingerprinting System


## Backend development — retained Milestone 1 mock endpoint

A **working synchronous HTTP prototype** now lives in [`backend/`](backend/). It accepts one user prompt, feeds synthetic target replies into the existing `PromptAnalysisService`, requests the real six Harness v1 probe prompts through a mock `TargetClient`, and returns a JSON report marked `mode: "mock"`. That **mock route** does not use real model inference, user keys, provider APIs, a live judge, historical baselines or cards. A separate OpenAI target route was added in Milestone 2. Stage 1 stays off by default.

```bash
python -m pip install -r system/requirements-backend.txt
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
# Visit http://127.0.0.1:8000/docs
```

Run these commands from the **parent GitHub repository root** after installing `system/requirements-integrated.txt` into the same environment. See [`docs/BACKEND_MILESTONE1.md`](docs/BACKEND_MILESTONE1.md) and [`backend/README.md`](backend/README.md). The separate per-analysis OpenAI key input and target provider are implemented in Milestone 2; authenticated workers and saved-model history belong to later milestones (`TBD.md`).

This entire subsystem belongs in **`system/` at the root of the team's GitHub repository**. It contains the versioned Stage 1 and Stage 2 classifiers, pipeline, tests, evaluation, example workflows, and documentation. There is no second project root inside it.

## Current status (November 18, 2026)

- **UI flow:** Users enter **one prompt**. Their existing/authorized provider connection (including their API key, managed by the backend) supplies the initial reply. The pipeline automatically requests any required fingerprinting probes from **that same target deployment**. The UI does **not** ask users to paste a response or six probe answers.
- **Default identification:** Stage 1 is **OFF**. Stage 2 runs `LoRA → Harness → Random Forest` with fallback. Stage 1 can be enabled per run only when a previous/expected model identity is available.
- **LoRA checkpoint:** Uploaded `my_lora_adapter.zip` is installed as **`models/lora/v2/`**. Its configuration is **Qwen2.5-0.5B, rank 16, alpha 32**, and it includes a five-class `score.weight` head. `lora/v1` remains unchanged as the earlier metadata-only, Qwen2.5-1.5B experiment declaration. `lora/v2` is SHA-256 checksummed and passes **file readiness**, but its base revision is temporarily `main`, its label order is **provisional** (so it intentionally does **not** emit named candidates), real inference and notebook parity are **not tested**, and its decisions remain **review-only**. See `TBD.md` before live deployment.
- **Harness:** Offline replay and integration work; live provider judge is **not validated**. Six versioned probes can be collected by `TargetClient.ask` if the backend provides an authorized connection.
- **Random Forest:** Fitted five-class classifier and 52-feature extractor included; candidate-only until unknown-model rejection is calibrated.
- **Cards and changed information:** `PromptAnalysisService` reports *card availability* and a model/card change summary **only when reliable identifiers and authoritative card snapshots are supplied**. Model-card retrieval, historical snapshots, and secure user API connections still need to be provided by the backend. The HTTP prototypes ship **mock-only** and **live OpenAI target with mocked judge** routes; neither constitutes validated production identification.

**Integration documentation:** [UI handoff](docs/UI_INTEGRATION.md) · [Backend handoff](docs/BACKEND_INTEGRATION.md) · [Unresolved work](TBD.md) · [Evaluation](docs/UNIFIED_EVALUATION.md). For the long implementation history, see [archived notes](docs/IMPLEMENTATION_HISTORY.md).

## Repository placement

```text
Your-existing-GitHub-repo/
├── system/
│   ├── backend/                       # FastAPI mock M1 + live-target M2
│   ├── fingerprinting/
│   │   ├── adapters/
│   │   ├── workflow.py                  # One-prompt -> response -> probes -> fingerprint/card/change
│   │   ├── pipeline.py                  # Stage 1 optional, Stage 2 default
│   │   └── ...
│   ├── models/
│   │   ├── lora/v1/                    # Historical placeholder
│   │   ├── lora/v2/                    # Uploaded 0.5B checkpoint + checksums
│   │   ├── harness/v1/
│   │   ├── random_forest/v1/
│   │   └── stage1_lr/v1/
│   ├── catalog/
│   ├── config/
│   ├── tests/
│   ├── examples/
│   ├── docs/
│   ├── reports/
│   ├── requirements-backend.txt
│   ├── TBD.md
│   ├── run.py
│   └── README.md
├── collector/
└── ...other team projects...
```

## Root-level commands

```bash
python -m pip install -r system/requirements-integrated.txt
python system/run.py test
python system/run.py config --require-ready
python system/run.py example prompt_workflow_mock_demo
python system/run.py example stage2_default_real_demo
python system/run.py evaluate --rf-pilot --scope stage2 --methods random_forest
```

The prompt workflow demo is **fully synthetic** and makes no API calls or real identification claims. `config --require-ready` checks **file existence and hashes only**; it does NOT certify LoRA runtime loading, class mapping, model quality, live Harness credentials, or availability of model cards.

For LoRA inference, install separately:

```bash
python -m pip install -r system/requirements-lora.txt
```

The base Qwen model must also be downloadable or cached. Live LoRA inference has **not** been validated in this package. Before accepting any real identification claims, confirm the checkpoint's class mapping, pin its actual Hugging Face training commit, reproduce notebook predictions, and calibrate unknown-model rejection. The current `base_model_revision: main` is provisional and not deployment-grade.

## Backend-neutral prompt-first workflow

From the parent repository root:

```python
from pathlib import Path
from system.fingerprinting.clients import CallableTargetClient
from system.fingerprinting.workflow import BaselineSnapshot, PromptAnalysisService

# Given a factory-built `pipeline` and loaded `catalog`:
service = PromptAnalysisService(pipeline, catalog, card_resolver=backend_card_resolver)

# backend_provider_send(text) uses the already-authorized user connection;
# credentials are never passed into PipelineResult or PromptAnalysisService.
client = CallableTargetClient(backend_provider_send)
report = service.analyze(
    'Explain recursion in Python', client,
    request_id='job-123', deployment_id='authorized-deployment',
    baseline=BaselineSnapshot('llama3.1-8b', previous_card_snapshot),
    domain='risk', use_stage1=False,
)
response_json = report.to_dict()
```

The backend must obtain the provider-specific target model/endpoint and user authorization *before* calling `analyze()`. The original prompt is asked once; if the Harness runs, its six versioned probes are asked on the same connection. The classifier does not receive the provider's target-model ID as a ground-truth label. Do not commit user keys or send them to an untrusted URL.

`final.model_id` represents an **accepted** identification, not an unaccepted LoRA/RF candidate. If none is accepted, the UI shows `needs_review`, with no authoritative model card or change claim. Model-card field comparisons require both the current authoritative card and a previous saved card snapshot; absence produces `not_comparable`. If no baseline exists, report `no_baseline`, not "unchanged".

## What still is not implemented

No **production** authenticated job/connection HTTP endpoints, credential vault, live job queue, persistent deployment history, authoritative card service, or production-grade model-change dashboard are supplied. The new M3 SQLite queue is **mock-only and local-development-only**. Two **local-only** analysis routes are implemented: mock M1 and live OpenAI target with mock judge M2. A local-only mock `/jobs` contract is implemented; production jobs are **not**. See [`TBD.md`](TBD.md) for owners, blockers and release criteria.
