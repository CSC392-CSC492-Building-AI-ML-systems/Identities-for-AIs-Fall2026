# Consolidated repository

See the [root README](../README.md) and [migration guide](docs/REPOSITORY_CONSOLIDATION.md) for the current layout. Historical milestones below may describe superseded paths; `collector/` is now `system/collector/`, root `scripts/` moved to `system/research/stage1/`, and tests/fixtures live at the repository root.

# Latest prototype update — automated evaluation and reviewed publication

See [Release workflow](docs/RELEASE_WORKFLOW.md) for CPU-only RF comparison, `training run --evaluate-candidates`, explicit review-profile publication and rollback. No automatic activation, identity acceptance, live judge or real LoRA validation. Stage 1 remains deferred.

---

# Latest prototype update — model and family onboarding

Use `python system/run.py onboard-model status` to audit catalog/collector/card coverage. See [Model and family onboarding](docs/MODEL_FAMILY_ONBOARDING.md) for registration, draft research cards, reviewed publication and handoff to existing dataset/training tools. No new target identity or artifact was activated in this release.

---

# Latest prototype update — live Stage 2 review

See [CPU-only replay and PowerShell setup](docs/BACKEND_STAGE2_REVIEW.md) for the new opt-in Factory-driven RF/Harness live job mode. Stage 1 deferred; LoRA GPU validation pending. Existing mock workflows remain supported.

---

## Harness reference builder (current update)

`harness/v2` is a registered 17-model, six-probe, review-only reference candidate. See [Harness reference builder](docs/HARNESS_REFERENCE_BUILDER.md). RF, LoRA and Harness training/maintenance strategies are registered; Stage 1 is deferred and is not part of the prototype training roadmap. The live backend and production selection are unchanged.

## Automated LoRA training (current update)

The notebook-derived LoRA strategy is registered alongside RF. See [LoRA training guide](docs/LORA_TRAINING.md) and [actual data preview](reports/lora_candidate_data_preview.json). A real pinned base revision and training environment are required; no new trained checkpoint or runtime validation is claimed. Review-only, no auto-activation.

## New: multi-prompt Random Forest and teammate intake

The training orchestrator now has a real RF fixed-probe strategy. See
[RF_MULTI_PROMPT.md](docs/RF_MULTI_PROMPT.md) and
[TEAM_BRANCH_REVIEW.md](docs/TEAM_BRANCH_REVIEW.md). `random_forest/v2` is a
registered, review-only 17-class candidate (five selected probes). Use
`config/experiments/rf_panel_v2.yaml` for offline replay; the default production
configuration and live mock-judge worker are unchanged. The new Agentic raw
snapshot and fixed-probe split retain successful blank responses. The other
trainer implementations remain pending.

## Training orchestration foundation — November 26, 2026

Use `python system/run.py training methods`, `training plan --config
config/training/nov26_candidate.json`, and `training history`. See
[Training Orchestrator](docs/TRAINING_ORCHESTRATOR.md). All method-specific
trainers are explicitly blocked until finalized training/reference code arrives;
no model was retrained or activated. Refined dataset onboarding retains blank
responses without recorded errors (new `candidate_include_blank_seed42` split),
verifies existing splits, and binds classifier templates to local split hashes.

For the approved obsolete legacy cleanup and conditional inactive derived-data
cleanup, see [Legacy Cleanup](docs/LEGACY_CLEANUP.md). Run the checked migration
helper against the real repository after merging; a ZIP overlay cannot delete
old root paths. Other cleanup proposals remain pending. Production auth and
confidence thresholds are deferred for the local research prototype.

## Dataset onboarding — prototype (November 26, 2026)

New offline CLI: `python system/tools/onboard_dataset.py --help`. Validate ZIP/raw
collections, register immutable snapshots, create reproducible prompt-grouped
candidate splits, audit overlap, and export selected original rows. See
[Dataset Onboarding](docs/DATASET_ONBOARDING.md). The included November 26 example
split is not a certified holdout; pinned Harness reference overlap remains.
No classifiers, production configuration or backend behavior changed.

## Classifier artifact onboarding (November 26, 2026)

New local CLI: `python system/tools/onboard_classifier.py --help` from the repository root.
Use `template`, `validate`, `register --trust-bundle`, and `candidate-config` for
versioned teammate submissions. See [Classifier Onboarding](docs/CLASSIFIER_ONBOARDING.md).
Registration is metadata/file validation only, not real inference, threshold approval,
or automatic activation; the backend remains in its existing development mode.

## Updated collector dataset — November 26, 2026

The team's new raw collection is staged at [`datasets/collector_raw/2026-11-26/`](datasets/collector_raw/2026-11-26/README.md): 20 JSONL files, 9,717 records, 17 catalog IDs and six families. See the [dataset manifest](datasets/collector_raw/2026-11-26/manifest.json) for file hashes and quality counts. The existing trained models, Harness reference bundle, config selections and evaluation data remain unchanged while the ML team reruns models. New model releases must reference their exact dataset/split and pass validation before activation. Raw data is not a frozen evaluation split; review permissions and privacy before publishing it to GitHub.

---

## Backend Milestone 6 — Linked jobs and unified frontend results (November 25, 2026)

Implemented: `POST /api/v1/fingerprint/live-jobs` now accepts an optional **owned**
`deployment_id`; the server derives the target routing ID and pins that
submission's reviewed baseline revision. `GET /api/v1/deployments/{id}/jobs`
lists linked jobs without secrets, and completed jobs expose typed
`result.ui_result` containing identification, comparison, model-card, and evidence
states. **Live judge stays mocked**, so identity and drift remain unconfirmed.
Existing unlinked live jobs and previously reviewed history are unchanged.
See **[docs/BACKEND_MILESTONE6.md](docs/BACKEND_MILESTONE6.md)** for actual
request/response formats, Windows Git Bash instructions, and security limits.
No additional legacy cleanup has been performed beyond C1.

---

## Backend Milestone 5 — model cards and reviewed deployment history (prior milestone)

## Stage 1 script deduplication (C1 — November 22, 2026)

**After merging the ZIP into an existing checkout**, run the checked migration
helper so old copies actually disappear (ZIP extraction doesn't delete files):

```bash
python system/tools/apply_c1_cleanup.py          # Dry run
python system/tools/apply_c1_cleanup.py --apply  # Apply checked deletion
```

The 17 historical Stage 1 **research scripts** remain at the **GitHub repository
root** in `scripts/` and are no longer duplicated under
`system/reference_stage1/scripts/`. This cleanup **does not remove Stage 1
verification**, its trained `models/stage1_lr/v1/` artifacts, or the opt-in
`use_stage1` switch. The parity test imports `../scripts/` when the full
repository is present; only that original-source comparison is skipped if
`system/` is distributed alone. All other system tests remain runnable.

The `stage1_lr/v1` manifest's old `provenance.source_script` is retained as an
**immutable historical release reference**; the current canonical research
source is `scripts/predict_hierarchical.py` at the repository root. See
[the migration report](docs/CLEANUP_C1_MIGRATION.md) and
[cleanup decisions](CLEANUP_REVIEW.md). No other cleanup items were removed.


The FastAPI backend now reads the team's **authoritative sibling `cards/` folder** and stores owner-scoped **manually reviewed** baseline snapshots; it never promotes a classifier candidate automatically. APIs include `GET /api/v1/models/{model_id}/card`, `POST /api/v1/deployments`, reviewed `POST /baselines`, `GET /history` and `GET /changes`. Stage 1 remains opt-in; M4 worker/live provider routes are unchanged.

From the GitHub repository root, with `cards/`, `collector/` and `system/` as siblings, see **[`docs/BACKEND_MILESTONE5.md`](docs/BACKEND_MILESTONE5.md)** for Windows Git Bash commands and API examples. All proposed legacy removals are documented—**none performed**—in **[`CLEANUP_REVIEW.md`](CLEANUP_REVIEW.md)**. 

---

## Backend Milestone 3 — durable mock jobs (NEW)

## FastAPI Backend M4 — local authenticated live jobs

The subsystem now provides **authenticated live OpenAI-target analysis jobs**
(`POST /api/v1/fingerprint/live-jobs` and owner-scoped GET) processed by a
separate worker. A per-analysis provider key is stored in a temporary **encrypted
local vault file, not SQLite**, while queued prompts/results are encrypted in
SQLite. This is a local development mechanism, NOT a production authentication
service, managed secrets or validated model identity. The Harness judge is mocked.

See [`docs/BACKEND_MILESTONE4.md`](docs/BACKEND_MILESTONE4.md) for Windows Git Bash
commands, three-terminal startup and a secure interactive client. Existing mock
endpoints and test commands are unchanged. The old unauthenticated synchronous
live endpoint is disabled by default.


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
