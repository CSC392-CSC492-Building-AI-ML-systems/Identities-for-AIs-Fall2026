# Live Stage 2 review prototype (M7 functional integration)

This replaces the need to wait for LoRA GPU training before demonstrating a real trained classifier. It is an **opt-in, localhost-only** profile, not production authentication or an acceptance policy. Stage 1 is deferred. No new weights were trained. Production YAML, existing artifacts, raw datasets and historic code are preserved.

## What is available

`config/experiments/live_stage2_review.yaml` builds Harness v2 and multi-probe RF v2 using the existing Factory and prompt-first workflow. Default judge is a deterministic abstaining mock: no synthetic candidate. RF uses the real trained weights. Harness gathers six probes and RF reuses its selected five. Matching probe text/ID is checked at startup and there is a maximum of six distinct additional probes. Failed probes are not reissued within one job. LoRA is explicitly not configured until its checkpoint is pinned and labels confirmed; CPU inference may be used after training elsewhere. The older LoRA v2 checkpoint is intentionally refused by this profile. A future `lora/v3` can be placed before Harness in a copy of this YAML once its registered weights, mappings, review-only policy and base commit are ready. No Stage 1 loading or automatic card resolution is allowed in this profile.

## CPU-only offline demo (PowerShell, repository root)

Use the project's Python 3.11+ virtual environment. If creating a new one:

```powershell
python -m venv .venv-demo
.\.venv-demo\Scripts\Activate.ps1
python -m pip install -r system/requirements-integrated.txt
python -m pip install -r system/requirements-backend.txt
python system/tools/demo_stage2_replay.py
```

If script execution is blocked, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` then retry activation, or directly invoke `.\.venv-demo\Scripts\python.exe`. A GPU, model download and judge/API credentials are not required for this demo. It replays a stored Claude Haiku 4.5 trace (with a synthetic initial reply) through RF v2 and a mock judge. See `reports/stage2_cpu_replay.json`. It is a demonstration, not a new independent accuracy estimate. The score is not a calibrated probability.

## Live prototype on your machine (PowerShell)

Stop old API and workers before updating; older code does not know the new job mode. Back up existing dev DB. Keep localhost only. Use the same virtual environment in each terminal. The dev token and encryption file from M4 remain in use, not production login. If you haven't set them up yet:

```powershell
python -m system.backend.security.setup_dev_auth --user developer
python -m system.backend.security.setup_dev_crypto
```

Save token privately. Rerunning auth provisioning rotates that user's token. Never regenerate an encryption key for existing records. Both terminals must use the same key and DB; use the existing key file:

Terminal A:

```powershell
.\.venv-demo\Scripts\Activate.ps1
$env:SYSTEM_JOB_FERNET_KEY = (Get-Content system/.local/dev_job.key -Raw).Trim()
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000
```

Terminal B:

```powershell
.\.venv-demo\Scripts\Activate.ps1
$env:SYSTEM_JOB_FERNET_KEY = (Get-Content system/.local/dev_job.key -Raw).Trim()
python -m system.backend.worker --kind stage2 --loop --poll-seconds 1
```

Terminal C:

```powershell
.\.venv-demo\Scripts\Activate.ps1
python -m system.backend.dev_live_job_client --stage2 --model YOUR_PROVIDER_ROUTING_ID
```

Enter prompt, development bearer token and your authorized OpenAI target key when prompted. Target routing ID is not inferred identity. Up to seven target requests (initial + six probes) are billable. Use a capped development account. The current provider adapter rejects missing/empty usable text; successful blank-response transport semantics and structured provider refusals still need separate live validation (offline training retains eligible blanks). Old `--kind live` workers and default request mode remain legacy/mock; the new worker processes only `live_stage2_review` rows. Do not run old binary versions against the migrated database.

## API handoff

Use existing authenticated POST `/api/v1/fingerprint/live-jobs` and GET `/api/v1/fingerprint/live-jobs/{job_id}`; `GET /api/v1/deployments/{id}/jobs` still lists linked jobs. Explicit request:

```json
{"mode":"live_stage2_review","allow_live_judge":false,"provider":"openai","target_model":"YOUR_PROVIDER_ROUTING_ID","prompt_text":"Explain recursion.","api_key":"USER_TARGET_KEY","use_stage1":false}
```

Or substitute an owned `deployment_id` for `target_model`. M6 behavior and baseline pinning remain. Omit `mode` to retain legacy behavior. POST returns 202 with `mode` and job_id; GET returns original lifecycle status. `result.ui_result.method_candidates` contains one row per method (`method`, `artifact_id`, `status`, `candidate_model_id`, `score`, `score_type`, `probe_ids_used`). Statuses: `candidate`, `abstained`, `error`, `not_configured`, `mock_judge`. `candidate_agreement` is `none`, `single_candidate`, `agree`, or `disagree` among named candidates only; not a verified identity. A completed job is not necessarily successful inference. `result.status` may be `error` or `needs_review`. `result.ui_result.evidence.judge` is the configured judge transport, not proof of a successful call. Report has only allowlisted method evidence and artifact/config IDs, not raw arbitrary judge messages, responses or errors. `accepted_model_id` and change/card comparison remain unset; reviewed baseline remains unchanged. Use existing model-card endpoint for an explicitly labeled candidate reference if desired, not as a confirmed target card. `capabilities.stage2_review_jobs_supported` describes the API contract, not worker liveness. `live_judge_available` stays false because API cannot attest worker credentials/readiness. OpenAPI: `OPENAPI_STAGE2.json`.

## Optional real Harness judge (not needed for CPU demo)

Default no external judge. To use the existing pinned Harness v2 judge path, operator must explicitly start `--kind stage2 --allow-live-judge` and configure `GEMINI_API_KEY` (or `OPENAI_API_KEY` for a review-only artifact configured for OpenAI) in the worker process only. Use a private mechanism to set the environment variable, not a committed file or key in a command history. The supplied manifest selects Google and `gemini-3.8-flash`; independently confirm actual availability and account authorization before trying. A user's target key is never used as the judge key. The job must additionally set `allow_live_judge:true` (client `--stage2 --allow-live-judge`). This expressly authorizes sending observed probe responses and reference examples to that judge provider; do not use confidential prompts/data. Consent is encrypted in the job input. Without worker enablement, consenting jobs fail `JUDGE_NOT_CONFIGURED` before target calls. If user doesn't consent, mock judge is used even by a worker that supports the real one. Existing judge transport/retries/timeouts remain; extra judge calls/costs may occur. No real live judge or target requests were executed for this release. Do not claim actual live performance, calibrated scores, unknown rejection, or production readiness.

## Validation

```powershell
python -m unittest tests.core.test_backend_stage2 -v
```

89 backend tests passed in the final run, including all 11 new Stage 2 tests. 82 core Factory/pipeline/workflow/RF/registry tests passed when run from `system/` (the initial root invocation of those modules failed because they use `fingerprinting` imports). Independent worker startup against an empty temporary DB passed; no API call. The full historical suite was not rerun. Existing SQLite ResourceWarnings appeared in backend tests. Actual GPU training, genuine provider/judge smoke testing, broader model validation and final acceptance policy remain open. Production authentication and Stage 1 are deferred. Next: end-to-end demo with authorized real provider, then real LoRA artifact integration when available; model/family onboarding and repository consolidation remain pending.
