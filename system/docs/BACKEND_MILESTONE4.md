# Backend Milestone 4 — Authenticated live background jobs (local development)

**Status:** Implemented and offline tested. This milestone extends M3's durable SQLite
mock jobs with a **separate, authenticated, encrypted, live OpenAI-target job path**.
It is **not** a public multi-user deployment, a production secret vault, or a
validated model-identity system. **The Harness judge is still mocked.**

## What changed

| File | Responsibility |
|---|---|
| `backend/security/auth.py` | Authenticate local bearer tokens; job ownership comes from the authenticated token, not caller-supplied user IDs |
| `backend/security/setup_dev_auth.py` | Provision a high-entropy local bearer token and store its SHA-256 digest, never plaintext token |
| `backend/security/crypto.py` | Fernet encryption of prompts/results; separate ephemeral encrypted credential files indexed by unpredictable UUID job IDs |
| `backend/security/setup_dev_crypto.py` | Generate an ignored local development encryption-key file for two-terminal testing |
| `backend/jobs/live_store.py` | Durable, owner-scoped live jobs, encrypted input/result, queue expiry, atomic worker claim, no automatic retries |
| `backend/jobs/live_runner.py` | Decrypt job, load short-lived user key from vault, call live target gateway, encrypt result and delete credential file |
| `backend/worker.py` | `--kind live` supports a separate live worker (default `mock` remains intact) |
| `backend/app.py` | Authenticated live-job POST/GET endpoints; legacy unauthenticated synchronous live route disabled by default |
| `backend/dev_live_job_client.py` | Interactive localhost test client; getpass for bearer token and user provider key |
| `tests/test_backend_live_jobs.py` | Fake-provider tests for seven queries, key isolation, encryption, cross-user access, expiry, worker errors and cross-process cleanup |

## API contract

`POST /api/v1/fingerprint/live-jobs` requires `Authorization: Bearer <local-app-token>`.
The JSON contains **one prompt**, the provider routing ID and the user's key:

```json
{
  "prompt_text": "Explain recursion in Python.",
  "provider": "openai",
  "target_model": "YOUR_OPENAI_API_MODEL_ID",
  "api_key": "USER_KEY_ENTERED_IN_SECURE_FORM",
  "use_stage1": false
}
```

- HTTP `202`: `{ "job_id": "...", "mode": "live_target_mock_judge", "status": "queued", "created_at": "...", "schema_version": "1.0" }` with a `Location` header pointing to the GET endpoint.
- `GET /api/v1/fingerprint/live-jobs/{job_id}` uses the **same bearer token**. Returns `queued`, `running`, `completed`, or `failed`, and a completed report or a generic error code.
- Another user's token returns `404` (the job's existence is not disclosed).
- Missing/invalid token returns `401`; an unconfigured authenticated service returns `503`.
- `use_stage1=true` returns `409` until confirmed deployment baselines are implemented.
- No requested provider/model identity is used as ground-truth input to fingerprinting.
- A `needs_review` result is expected: the system currently uses a mock Harness judge. **Do not show an accepted model or model-card change as confirmed.**

The original `POST /api/v1/fingerprint/jobs` and corresponding GET are **mock-only**
local training endpoints and remain unauthenticated to preserve M3 examples. They
cannot access authenticated live-job records. `POST /api/v1/analyze/live`, the
old synchronous route, is **disabled by default** (404); it can be explicitly
re-enabled only for localhost development via
`SYSTEM_ENABLE_LEGACY_SYNC_LIVE=1`.

## Windows Git Bash — local setup, from GitHub repository root

### 1. Install dependencies in Python 3.11+

```bash
source .venv/Scripts/activate
python -m pip install -r system/requirements-integrated.txt
python -m pip install -r system/requirements-backend.txt
```

### 2. Provision a local application bearer token

```bash
python -m system.backend.security.setup_dev_auth --user developer
```

The command **prints the bearer token once**. Save it in a password manager
and use it in the interactive client. The local ignored
`system/.local/dev_users.json` file contains **only its SHA-256 digest**.
This is a high-entropy development API token, not a login system: there is no
email/password sign-in, expiry, refresh token, self-service account recovery,
revocation endpoint, OAuth/OIDC, CSRF/cookie session design or audit service.
Running the command again rotates the user's token; restart FastAPI to reload
its auth file.

### 3. Set up a shared development encryption key

```bash
python -m system.backend.security.setup_dev_crypto
```

This creates ignored `system/.local/dev_job.key`, without replacing an existing key.
The key file is **plaintext** and is on the same developer machine as encrypted
SQLite/vault files. This is only a local teaching convenience; it is not production
key management. Do not commit or share `.local/`, do not store key or bearer tokens
in Git history, do not use real private user data, and don't expose the API publicly.

### 4. Start the API (Git Bash terminal 1)

```bash
source .venv/Scripts/activate
export SYSTEM_JOB_FERNET_KEY="$(cat system/.local/dev_job.key)"
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

### 5. Start the live worker (Git Bash terminal 2)

```bash
source .venv/Scripts/activate
export SYSTEM_JOB_FERNET_KEY="$(cat system/.local/dev_job.key)"
python -m system.backend.worker --kind live --loop --poll-seconds 1
```

Use the same encryption key and local database in **both processes**. The default
path is `system/.local/jobs.sqlite3`. If using `SYSTEM_JOB_DB_PATH`, set the same
absolute path in both terminals. The default worker kind is `mock`, so the
`--kind live` flag is important.

### 6. Send a controlled test request (Git Bash terminal 3)

```bash
source .venv/Scripts/activate
python -m system.backend.dev_live_job_client --model YOUR_OPENAI_MODEL_ID
```

You will be prompted for one prompt, your **local backend bearer token** and
**your OpenAI provider API key**. Both credentials are entered without terminal
echo or embedding them in a command-line argument. The client POSTs the job and
polls the result. The browser's Swagger UI at `http://127.0.0.1:8000/docs`
is also available, but entering secrets there exposes them to browser tools;
prefer the interactive script for development.

**Cost warning:** A successful example may issue up to seven billable target
requests (initial user prompt plus six Harness probes). Provider calls are
bounded per request and have no automatic retries; not all model IDs support
all parameters. The *judge* is still a fake and makes no external calls. No
billable API requests are made by the unit tests.

## Security details and limits

- The **user's provider key never enters SQLite**. FastAPI writes it only to an
  encrypted, short-lived `.local/live_secrets/<uuid>.secret` file, with local
  file permissions where supported. The queue row contains the job UUID but
  not the raw key. The API and worker both need the Fernet key.
- The queued **prompt and model routing ID** are encrypted in SQLite; the
  completed response/report is encrypted too. API results are restricted by
  the bearer token's owner ID. The token hash mapping is local-only.
- Credentials are deleted after completion/failure. Queued jobs expire after
  ten minutes; abandoned running jobs are failed after fifteen minutes when a
  worker next checks. Crashed or halted workers can delay cleanup. Filesystem
  backups, SSD snapshots and swap may retain encrypted file bytes, and a user
  or attacker with the **encryption key** can decrypt them. Key file and data
  co-location defeats many at-rest attacker scenarios.
- Job retries are disabled to reduce duplicate billing. A claimed job that
  loses its worker is not automatically rerun. There is not yet a real
  heartbeat, cancellation, exactly-once upstream semantics, quotas, rate
  limits, standardized error taxonomy, secrets manager or retention scheduler.
- Sending a provider key in a JSON request still requires HTTPS for any remote
  connection; these examples deliberately bind to **127.0.0.1 only**. Debug
  middleware/proxies/monitoring/browser extensions must not record requests.
- Local bearer tokens authenticate users only within this prototype. Before
  going public, replace with trusted identity provider/OIDC, managed secrets,
  proper user/session storage, audit trails, database authorization, retention
  and cost limits. See `system/TBD.md`.

## Tests

From the GitHub repository root:

```bash
python -m unittest system.tests.test_backend_live_jobs -v
python system/run.py test
```

These are deterministic offline tests; they use a **fake OpenAI transport**
for the seven-query request path, verify encrypted at-rest data and owner isolation,
exercise SQLite concurrency and expiry, and verify that a separate live worker
process can clean up an expired job without making provider requests.

**Next milestone:** production-style authentication, managed credential vault and
provider consent/quotas, or confirmed deployment baselines and persistent model
cards/history. Prioritize real provider smoke test and explicit judge authorization.
