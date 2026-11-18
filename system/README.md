# LLM Fingerprinting System

This entire subsystem belongs in **`system/` at the root of the team's GitHub repository**. It contains the versioned Stage 1 and Stage 2 classifiers, pipeline, tests, evaluation, example workflows, and documentation. There is no second project root inside it.

## Current status (November 18, 2026)

- **UI flow:** Users enter **one prompt**. Their existing/authorized provider connection (including their API key, managed by the backend) supplies the initial reply. The pipeline automatically requests any required fingerprinting probes from **that same target deployment**. The UI does **not** ask users to paste a response or six probe answers.
- **Default identification:** Stage 1 is **OFF**. Stage 2 runs `LoRA → Harness → Random Forest` with fallback. Stage 1 can be enabled per run only when a previous/expected model identity is available.
- **LoRA checkpoint:** Uploaded `my_lora_adapter.zip` is installed as **`models/lora/v2/`**. Its configuration is **Qwen2.5-0.5B, rank 16, alpha 32**, and it includes a five-class `score.weight` head. `lora/v1` remains unchanged as the earlier metadata-only, Qwen2.5-1.5B experiment declaration. `lora/v2` is SHA-256 checksummed and passes **file readiness**, but its base revision is temporarily `main`, its label order is **provisional** (so it intentionally does **not** emit named candidates), real inference and notebook parity are **not tested**, and its decisions remain **review-only**. See `TBD.md` before live deployment.
- **Harness:** Offline replay and integration work; live provider judge is **not validated**. Six versioned probes can be collected by `TargetClient.ask` if the backend provides an authorized connection.
- **Random Forest:** Fitted five-class classifier and 52-feature extractor included; candidate-only until unknown-model rejection is calibrated.
- **Cards and changed information:** `PromptAnalysisService` reports *card availability* and a model/card change summary **only when reliable identifiers and authoritative card snapshots are supplied**. Model-card retrieval, historical snapshots, and secure user API connections still need to be provided by the backend. No real HTTP server is shipped.

**Integration documentation:** [UI handoff](docs/UI_INTEGRATION.md) · [Backend handoff](docs/BACKEND_INTEGRATION.md) · [Unresolved work](TBD.md) · [Evaluation](docs/UNIFIED_EVALUATION.md). For the long implementation history, see [archived notes](docs/IMPLEMENTATION_HISTORY.md).

## Repository placement

```text
Your-existing-GitHub-repo/
├── system/
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

No HTTP endpoints, provider SDK integrations, credential vault, job queue, persistent deployment history, authoritative card service, or production-grade model-change dashboard are supplied. The guide describes the proposed API contract; its routes are **not implemented**. See [`TBD.md`](TBD.md) for owners, blockers and release criteria.
