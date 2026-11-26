# Identities for AIs — fingerprinting research prototype

Root-layout release. The supported workflow collects LLM responses, onboards datasets and identities, trains or refreshes Stage 2 classifiers, evaluates candidates, and serves review-only results. **Stage 1 is deferred.** LoRA training is implemented but a new real checkpoint has not yet been trained or evaluated. The CPU demo uses RF v2 and Harness v2 (mock judge). Do not interpret candidate results as verified changes.

## Repository layout

- `system/`: collector, runtime/backend, canonical catalog, raw snapshots/splits, versioned artifacts, training and release tools, documentation and reports.
- `tests/`: core tests, deferred research tests, and retained evaluation fixtures.
- `cards/`: authoritative model-card library, field schemas and existing research. The collector configuration and licence library now live in `system/collector/`.

## Quick start (Windows PowerShell, repository root)

Use Python 3.11+ and a new environment, or reuse a compatible environment. No GPU or API credentials are needed for the offline demo.

```powershell
python -m venv .venv-demo
.\.venv-demo\Scripts\Activate.ps1
python -m pip install -r system/requirements-integrated.txt
python -m pip install -r system/requirements-backend.txt
python system/run.py config config/experiments/live_stage2_review.yaml --require-ready
python system/tools/demo_stage2_replay.py
python system/run.py test
```

If activation is blocked, use the environment's `python.exe` directly (`.\.venv-demo\Scripts\python.exe` instead of `python`). The default test command runs the core suite from the root. Use `python system/run.py test --research` for historical Stage 1 research checks, or `--all` for both. Run filtered checks from the repository root, e.g. `python -B -m unittest tests.core.test_backend_stage2 -v`.

## Developer commands

`python system/run.py` exposes `config`, `example`, `evaluate`, `test`, `onboard-model`, `onboard-dataset`, `onboard-classifier`, `training`, and `release`. Except for tests, relative CLI paths remain relative to `system/`. Standalone collector/tools invoked directly resolve their explicit paths according to their own CLI; use repository-root paths in the commands below.

```powershell
python system/collector/collect.py --model mock-model --dry-run --limit 1
python system/run.py onboard-model status
python system/run.py training methods
python cards/show_card.py --family Llama
python system/run.py release history
```

## Guides

- [Repository migration and path changes](system/docs/REPOSITORY_CONSOLIDATION.md) — read before merging into an existing checkout.
- [Stage 2 backend, frontend contract and local live setup](system/docs/BACKEND_STAGE2_REVIEW.md)
- [OpenAPI contract](system/docs/OPENAPI_STAGE2.json)
- [Model/family onboarding](system/docs/MODEL_FAMILY_ONBOARDING.md), [dataset onboarding](system/docs/DATASET_ONBOARDING.md), [classifier onboarding](system/docs/CLASSIFIER_ONBOARDING.md)
- [Training orchestrator](system/docs/TRAINING_ORCHESTRATOR.md), [RF](system/docs/RF_MULTI_PROMPT.md), [LoRA](system/docs/LORA_TRAINING.md), [Harness](system/docs/HARNESS_REFERENCE_BUILDER.md)
- [Evaluation and publication](system/docs/RELEASE_WORKFLOW.md), [current backlog](system/TBD.md)

No local secrets, Git history, virtual environments, databases or unpublished training runs are shipped. Historical Stage 1 sources remain under `system/research/stage1/`; their derived data is no longer shipped. Raw datasets and registered immutable artifacts are retained. This is a local research prototype, not a production service. Review collection licences and access permissions before using or redistributing data.
