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

# Backend — FastAPI M4 (local development)

Three workflows are preserved:

1. `POST /api/v1/analyze` — synchronous offline mock.
2. `POST /api/v1/fingerprint/jobs` + GET — durable **mock-only** jobs.
3. `POST /api/v1/fingerprint/live-jobs` + GET — **authenticated** live OpenAI
   target jobs, processed by a **separate** worker. Key is stored only in a
   **temporary encrypted local secret file**, never plaintext in SQLite.

The earlier synchronous `/api/v1/analyze/live` is **disabled by default**.

Read **[Milestone 4 guide](../docs/BACKEND_MILESTONE4.md)** first. It includes
Windows Git Bash setup, local bearer token provisioning, encryption-key setup,
three-terminal API/worker/client instructions, endpoint contracts and privacy
limitations. Previous milestones remain in `../docs/BACKEND_MILESTONE{1,2,3}.md`.

All real target requests are potentially billable; the Harness judge is still
mocked and no real model identity is confirmed. Keep the server on `127.0.0.1`.
