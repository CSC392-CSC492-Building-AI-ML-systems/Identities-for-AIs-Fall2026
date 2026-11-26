# Backend Milestone 6 — Deployment-linked fingerprinting jobs and UI results

**Implemented for local development.** This release builds on M5 + approved C1 Stage 1 script deduplication. It **does not delete any further legacy files**, introduce production login, accept a live Harness judge, or make automated model-change claims.

## What was added

| File | Responsibility |
|---|---|
| `backend/ui_results.py` | A conservative, small and typed UI-facing presentation of live target / mock judge results |
| `backend/schemas.py` | Optional `deployment_id` and typed `UnifiedLiveResult` in OpenAPI; backwards-compatible unlinked requests |
| `backend/app.py` | Owner-check deployment linkage before the key is stored; resolve API routing model from deployment; list a deployment's jobs |
| `backend/jobs/live_store.py` | Additive SQLite migration, pinned baseline reference per job, encrypted request snapshot, indexed owner-scoped job listing |
| `backend/jobs/live_runner.py` | Attach the pinned baseline and safe `ui_result` when processing the job |
| `tests/test_backend_deployment_jobs.py` | Ownership, schema, migration, pinned-baseline, safe-result, regression, provider isolation tests |

## UI/API contract (implemented)

All routes below except `/health` use the existing **local development bearer token**. Real AI calls also require user-provided provider credentials. The API supports OpenAI *target routing* only; it does not infer model identity from that routing ID.

### Set up or select a monitored deployment

`POST /api/v1/deployments`:

```json
{"label":"My production AI alias","provider":"openai","requested_model_id":"my-provider-model-id"}
```

Returns HTTP 201 with `id`, `provider`, `requested_model_id`, and `baseline: null` until reviewed history is recorded. `GET /api/v1/deployments` lists the caller's deployments. A reviewer can record a reviewed baseline with `POST /api/v1/deployments/{id}/baselines` using `model_id`, `acknowledge_manual_review: true`, and a substantive `review_note`. **An analysis result never automatically adds or modifies a baseline.**

### Submit a linked live analysis

`POST /api/v1/fingerprint/live-jobs`, `Authorization: Bearer <development-token>`:

```json
{
  "prompt_text": "Explain recursion in Python.",
  "provider": "openai",
  "deployment_id": "a-owned-deployment-uuid",
  "api_key": "YOUR_OPENAI_KEY",
  "use_stage1": false
}
```

- **`deployment_id` is optional.** Without it, `target_model` is required, as in M4. With it, `target_model` may be omitted; the server retrieves the routing identifier from the deployment. If supplied, it must exactly match the registered routing ID (otherwise HTTP 409).
- A nonexistent deployment **or one belonging to another user** returns the same HTTP 404 *before creating the job or vault file*.
- Stage 1 still rejects `use_stage1: true` with HTTP 409 for live jobs. A saved reviewed baseline makes comparison metadata possible, but Stage 1 verification has not yet been safely wired into the live-worker inference path.
- Provider keys remain in the temporary encrypted vault outside the SQLite job table; the job input and pinned baseline metadata are sealed using the existing M4 encryption key.
- The prompt screen can show only a prompt input **if the selected deployment and short-lived key have been provided through a separate connection flow**. Saved keys are NOT implemented.

HTTP 202 response:

```json
{
  "schema_version": "1.0",
  "job_id": "generated-uuid",
  "mode": "live_target_mock_judge",
  "status": "queued",
  "created_at": "2026-11-25T20:00:00+00:00",
  "deployment_id": "a-owned-deployment-uuid",
  "baseline_revision": 1
}
```

The `baseline_revision` is `null` for deployments without reviewed history, or for unlinked jobs.

### Poll a job / show UI results

`GET /api/v1/fingerprint/live-jobs/{job_id}`. The status is `queued`, `running`, `completed`, or `failed`. Completed responses retain the old `result.report` research diagnostics and add this **small stable UI projection** at `result.ui_result`:

```json
{
  "schema_version": "1.0",
  "identification": {
    "status": "needs_review",
    "accepted_model_id": null,
    "reason": "live_judge_not_validated"
  },
  "comparison": {
    "status": "insufficient_evidence",
    "previous_model_id": "llama3.1-8b",
    "current_model_id": null,
    "identity_change": null,
    "family_change": null,
    "card_comparison": {"status": "not_comparable", "changes": []}
  },
  "model_card": {"status": "unavailable", "model_id": null, "card": null},
  "baseline": {
    "id": "previous-reviewed-baseline-uuid",
    "revision": 1,
    "model_id": "llama3.1-8b",
    "confirmation_source": "manual_review",
    "confirmed_at": "2026-11-25T20:00:00+00:00",
    "card_status": "available",
    "card_snapshot_sha256": "recorded-hash-or-null"
  },
  "evidence": {
    "target_provider": "openai",
    "judge": "mock",
    "identity_confirmed": false,
    "baseline_auto_updated": false
  }
}
```

These are illustrative field values. For no reviewed history, `baseline: null` and `comparison.status: "no_baseline"`. For current mock-judge jobs, **no new identity/card/change can be confirmed**. The report's `result.report` is technical diagnostics, not the recommended source of UI claims.

### List jobs by deployment

`GET /api/v1/deployments/{deployment_id}/jobs` → `{ "deployment_id": "...", "jobs": [...] }`. Each item contains `job_id`, `status`, `created_at`, `updated_at`, `baseline_revision`, `error_code` and **no secrets, prompt or raw report**. This route checks deployment ownership first. Existing reviewed `/history` and `/changes` endpoints continue to compare only approved manual baseline snapshots, not live candidate predictions.

## How baseline snapshot pinning works

When the POST request is authorized, the backend saves the current reviewed baseline's **ID, revision, model ID, confirmation time, card status and card digest** with the job. The worker uses that immutable reference even if reviewers add another baseline while the job is queued. It does **not** overwrite a baseline or generate card diffs from unconfirmed identity scores.

This is a schema/DB migration: `SqliteLiveJobStore.initialize()` safely adds nullable `deployment_id`, `baseline_id`, `baseline_revision`, `baseline_model_id` columns to an existing M4 SQLite table. Original unlinked live-job requests and previously persisted M4 rows remain supported. Copy/backup your local dev DB before upgrading. A production database must use managed migrations and backup testing.

## Run locally — Windows Git Bash

From the GitHub repository root:

```bash
source .venv/Scripts/activate
python -m pip install -r system/requirements-backend.txt
python -m system.backend.security.setup_dev_auth --user developer
python -m system.backend.security.setup_dev_crypto
```

Do not regenerate your existing dev auth/encryption files if you have active jobs/data: replacing the encryption key makes previous ciphertext unreadable. In two Git Bash terminals, using the **existing** saved key:

```bash
export SYSTEM_JOB_FERNET_KEY="$(cat system/.local/dev_job.key)"
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

```bash
export SYSTEM_JOB_FERNET_KEY="$(cat system/.local/dev_job.key)"
python -m system.backend.worker --kind live --loop --poll-seconds 1
```

Open `http://127.0.0.1:8000/docs` for OpenAPI/Swagger. Authorize with the development bearer token, create a deployment, optionally record a reviewed baseline, then submit a live job. **This can make real, billable provider requests** and should be attempted only with explicit consent and a capped development account.

To test without external requests:

```bash
python -m unittest tests.core.test_backend_deployment_jobs -v
python -m unittest tests.core.test_backend_live_jobs tests.core.test_backend_history -v
python system/run.py test
```

## Limitations and next work

- **This is still localhost-only development**: development bearer tokens, local encrypted files, SQLite baseline records (plaintext for manual notes), no HTTPS termination, real login, CORS policy, tenancy audit, rate limiting, or managed key service.
- User API keys are **not saved in personalization**; the UI needs a separate ephemeral key-entry step and should not persist it in browser storage.
- Stage 1 remains off for background jobs, **even with a baseline**. Opt-in needs a new supported live worker inference path and explicit compatibility checks.
- Live Harness **judge is mocked**, LoRA v2 mapping unvalidated, RF rejection uncalibrated. Consequently no current model identity or model-card comparison is promoted as confirmed.
- No progress percentages, cancellation, retries, full worker leases, per-user quota limits, immutable audit trails, connection entities, or automatic accepted-identity promotion exist.
- Do not build the main UI around `result.report` internals; use `result.ui_result` and check `status` / `error_code`.
