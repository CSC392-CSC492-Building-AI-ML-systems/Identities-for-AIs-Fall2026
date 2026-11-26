# Backend (FastAPI)

**Milestone 3:** Development-only local API with three paths:

- `POST /api/v1/analyze` — synchronous mock fingerprinting (M1)
- `POST /api/v1/analyze/live` — synchronous OpenAI target using a per-request
  user API key, **mock judge** (M2, opt-in billable provider requests)
- `POST /api/v1/fingerprint/jobs` and `GET /api/v1/fingerprint/jobs/{job_id}` —
  persistent **mock-only** jobs processed by an independent SQLite worker (M3)

From the parent GitHub root, after activating the Python 3.11+ environment:

```bash
python -m pip install -r system/requirements-integrated.txt
python -m pip install -r system/requirements-backend.txt
# Git Bash terminal 1
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
# Git Bash terminal 2
python -m system.backend.worker --loop --poll-seconds 1
```

Open http://127.0.0.1:8000/docs to try the mock job API.

See [Backend Milestone 3](../docs/BACKEND_MILESTONE3.md) for file roles,
SQLite job semantics, security considerations, examples and tests. Previous
milestones: [M1](../docs/BACKEND_MILESTONE1.md),
[M2](../docs/BACKEND_MILESTONE2.md).

**Not production-ready:** no auth, credential vault, live job worker, secure
storage for prompts, validated live judge, approved unknown-model rejection,
confirmed history or automatic model-card change detection. Keep bound to
`127.0.0.1` only; never submit real API keys to `/jobs`.
