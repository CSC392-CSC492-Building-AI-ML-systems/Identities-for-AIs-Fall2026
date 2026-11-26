# Backend Milestone 3 — Persistent mock jobs with SQLite and a separate worker

**Implemented and locally tested.** This milestone introduces a job lifecycle
while retaining both Milestone 1's synchronous mock route and Milestone 2's
request-scoped OpenAI target route. **It does not add queued live-provider
analyses, authenticated access, real judging, or confirmed model change.**

## What changed and why

The frontend used to wait for `POST /api/v1/analyze` to return the full report.
Now it can submit a mock analysis job, get a `job_id` immediately, and check
`GET /api/v1/fingerprint/jobs/{job_id}` until a separate worker finishes.
SQLite is intentionally used instead of Redis/Celery for this beginner-friendly,
local, zero-external-services milestone. One database file connects the API and
worker **across separate processes**. The worker uses an atomic SQL transaction
to claim each pending job exactly once during normal concurrent operation.

| File | Responsibility |
|---|---|
| `backend/jobs/store.py` | SQLite schema, durable job records, atomic claim, owner-checked terminal transitions and safe response projection |
| `backend/jobs/runner.py` | Runs the existing `MockAnalysisGateway`, serializes an `AnalyzeResponse`, saves success/failure |
| `backend/worker.py` | Independent worker command (`--once` / `--loop`) |
| `backend/app.py` | Adds POST and GET job endpoints; keeps older routes unchanged |
| `backend/schemas.py` | Strict Pydantic job request/status schemas |
| `tests/test_backend_jobs.py` | HTTP, database, concurrency, process-boundary and privacy regression tests |
| `.gitignore` | Excludes the local DB and WAL/SHM files |

## Windows Git Bash — from your GitHub repository root

Use Python 3.11+; the system's reconstructed Random Forest package requires it.

```bash
source .venv/Scripts/activate
python -m pip install -r system/requirements-integrated.txt
python -m pip install -r system/requirements-backend.txt

# Terminal A: FastAPI server
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Visit `http://127.0.0.1:8000/docs` and use `POST /api/v1/fingerprint/jobs`:

```json
{"prompt_text":"Explain recursion with a simple example.","use_stage1":false}
```

Or submit from a **second** Git Bash terminal:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/fingerprint/jobs \
  -H 'Content-Type: application/json' \
  -d '{"prompt_text":"Explain recursion.","use_stage1":false}'
```

Expect an immediate HTTP **202** with a `job_id`, `mode: "mock"` and
`status: "queued"`. Until the worker runs, polling the Location URL gives
`queued`, no result. In terminal B start the worker:

```bash
source .venv/Scripts/activate
# One job and exit:
python -m system.backend.worker --once

# OR run continuously until Ctrl+C:
python -m system.backend.worker --loop --poll-seconds 1
```

Poll via `GET /api/v1/fingerprint/jobs/{job_id}` in Swagger or `curl`.
The job state changes `queued → running → completed` (or `failed`). A
completed mock report contains `status: "needs_review"` and six Harness v1
probe IDs in addition to the initial `UI-INITIAL` question. This is **not** a
real model-identification result. Jobs remain after restarting the API process.

### State and result schema

**POST 202:**

```json
{
  "schema_version": "1.0", "job_id": "generated-uuid",
  "mode": "mock", "status": "queued", "created_at": "UTC-ISO8601"
}
```

**GET 200:**

```json
{
  "schema_version": "1.0", "job_id": "generated-uuid",
  "mode": "mock", "status": "completed",
  "created_at": "UTC-ISO8601", "updated_at": "UTC-ISO8601",
  "started_at": "UTC-ISO8601", "finished_at": "UTC-ISO8601",
  "attempt_count": 1,
  "result": { "schema_version": "1.0", "mode": "mock", "status": "needs_review" },
  "error_code": null
}
```

The `result` above is **abbreviated**. The actual `result` is the full
`AnalyzeResponse`, including `request_id`, `model_id`, `stage1_enabled`,
`model_card_status`, `change_status`, `target_queries`, and `report`.
Incomplete jobs return `result: null`; failures expose only an approved
`error_code`, not raw exception messages.

## Database and worker configuration

Default local SQLite path is `system/.local/jobs.sqlite3` and is excluded by
`.gitignore`. Both API and worker can use the **same** alternate path:

```bash
# Set this before starting BOTH server and worker
export SYSTEM_JOB_DB_PATH="$(pwd)/system/.local/dev-jobs.sqlite3"
```

Only the mock `/jobs` route writes to the job store. It rejects `api_key`,
`provider`, `target_model`, manually submitted `probes`, and any unexpected
fields with a redacted 422 error. It also rejects `use_stage1=true` with 409,
because no confirmed-baseline store exists yet. No provider credentials are
accepted or persisted in SQLite; the live OpenAI endpoint remains synchronous.

The database temporarily retains the **prompt in plaintext** while queued or
running, then sets the active row's `request_json` to NULL when completed or
failed. **This is not secure erasure:** SQLite WAL, the filesystem and backups
may retain old bytes. Only use non-sensitive mock prompts locally. Do not
publish the DB, allow remote access, or expose this development API publicly.

There is no login/ownership isolation. Any caller who knows a job ID could
retrieve its result on an exposed server. This is a **local-only learning
prototype**.

A worker interrupted after claiming a job leaves it `running`; we do not
requeue automatically because live inference may be billable and retries need
an idempotency policy. Stale-job recovery, retention policies, monitoring,
manual administrative control, authentication and worker resource isolation
are listed in `system/TBD.md`.

## Test

```bash
python -m unittest tests.core.test_backend_jobs -v
python -m unittest tests.core.test_backend_api tests.core.test_backend_openai_live -v
python system/run.py test
```

Tests include starting a **separate Python process** for a worker and proving
that the API can retrieve its completed result, a ten-worker concurrent-claim
scenario, safe error redaction, job state transitions, disallowed keys and
unavailable Stage 1. No test sends a real OpenAI request.

## What's next (M4)

1. Decide authentication and ownership; require it for all `/jobs` routes.
2. Decide how user-supplied secrets reach workers safely without placing
   them in SQLite requests or job queue payloads (short-lived encrypted secret
   vault/reference with expiry, access controls and explicit delete).
3. Add bounded live-provider jobs only after security, retry, timeout and cost
   controls are defined; eventually migrate to PostgreSQL and a managed queue
   as scale requires.
4. Add baseline/model-card history and a reviewed acceptance policy before
   claiming verified model changes.
