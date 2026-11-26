## Backend Milestone 2 — next work and known limitations

- [x] Add local, per-analysis OpenAI Responses API **target** adapter: fixed HTTPS endpoint, safe key handling in memory, bounded output, no retries, sanitized errors and fake-provider tests. See `docs/BACKEND_MILESTONE2.md`. This is not production authentication.
- [ ] Run a controlled **real** OpenAI target API smoke test with a development key and a supported API model; verify seven provider calls, measured latency, token cost and source output. No paid/API calls were made during automated tests.
- [ ] Design and implement authenticated users and per-user authorization before hosting the API publicly. Use HTTPS end-to-end, redacted request logging, quotas/rate limits, CSRF strategy (for any cookie sessions), and narrow CORS policy.
- [ ] Design a safe strategy for keys entered in personalization: server-side encryption/managed secrets, access controls, key rotation and deletion; avoid persistent browser localStorage. The current `/analyze/live` keeps keys only for its synchronous request.
- [ ] Move synchronous analyses to durable jobs/workers before live multi-user operation: bounded probe budgets, retry/cancellation policy, provider errors and auditability without storing secret contents.
- [ ] Add further providers only after the first one is verified. Provider and target deployment must be selected for API routing, never treated as ground truth for classification.
- [ ] Integrate real judge under explicit data-transfer consent. Current live route uses **mock judge** and cannot claim a confirmed fingerprint or validated card/change comparison.

# TBD — Release blockers and integration work

**Last updated: November 18, 2026 — Backend M3.** This is the active backlog for the `system/` GitHub subdirectory. Keep this file updated with owner, date, validation evidence and published artifact IDs. Previous milestone backlog is archived in [`docs/IMPLEMENTATION_TBD_HISTORY.md`](docs/IMPLEMENTATION_TBD_HISTORY.md). **Do not place credentials or private responses in Git.**

## Backend Milestone 1 — implemented (mock only)

- [x] FastAPI prototype `POST /api/v1/analyze`, `GET /health`, and `GET /api/v1/capabilities` with strict Pydantic request validation and **redacted 422 errors**. **Evidence:** `tests/test_backend_api.py`.
- [x] One prompt goes through real `PromptAnalysisService`, `CallableTargetClient`, and six **versioned Harness v1 prompts**, with a synthetic target and injected mock judge. No genuine identity result is claimed. **Evidence:** `docs/BACKEND_MILESTONE1.md`.
- [x] Dependency injection allows HTTP tests to swap the service without loading LoRA/RF or contacting any provider.

**Still open:** Real user API-key support, provider routing, authentication, background jobs, cards, confirmed history, and ML validation. Do not confuse the synchronous mock endpoint with a deployed service.

## Backend Milestone 3 — implemented (local mock queue only)

- [x] Persist mock analysis jobs in SQLite (`backend/jobs/store.py`) with
  `queued → running → completed/failed` states and atomic multi-worker claims.
- [x] Expose `POST /api/v1/fingerprint/jobs` and
  `GET /api/v1/fingerprint/jobs/{job_id}` in FastAPI, with strict input validation
  and generic error codes. Worker runs in a **separate process**, not an HTTP request.
- [x] Add `backend/worker.py` CLI (Git Bash compatible), tests of concurrent
  claims/restart persistence, and root-local ignored DB files.
- [x] Preserve the existing synchronous M1 mock and M2 live OpenAI-target routes.
- [ ] **Authentication and job ownership:** anyone knowing a job ID can access
  it in this prototype; do not expose to the network. Implement user scoping,
  authorization checks, audit logging and rate quotas before deployment.
- [ ] **Secure live-worker credential handoff:** current jobs REJECT API keys.
  For live jobs use a vetted encrypted, TTL-limited secret store or ephemeral
  broker, per-job access controls, and deletion on completion/timeout; NEVER
  place raw keys in SQLite/queue/result/logs. Decide user's key vs separate
  server judge credential and obtain data-transfer consent.
- [ ] **Privacy and retention:** prompts are stored in plaintext in a local
  SQLite job until completion. Clearing `request_json` does NOT erase WAL,
  backups or filesystem copies. Define encryption, retention/delete policy,
  access controls and record redaction before real users.
- [ ] **Worker recovery and reliability:** detect stuck `running` jobs after
  crashes; design leases/heartbeats, safe retry/idempotency, cancellation and
  timeouts. Avoid double-billing upstream providers during retries.
- [ ] **Production storage/queue:** evaluate Postgres + Redis/RQ/Celery or a
  managed queue when authenticated multi-instance deployment is required.

## Completed in this package

- [x] Imported real user-supplied `my_lora_adapter.zip` into **`models/lora/v2/`** with file hashes, adapter metadata, and a five-class `score.weight` head. **Important:** File/hash readiness ≠ real checkpoint inference or calibrated acceptance.
- [x] Preserved the old `lora/v1` metadata-only artifact, registered both versions and selected `lora/v2` in production/evaluation YAML.
- [x] Kept Stage 1 **off by default**, enabled only upon explicit opt-in with an expected identity.
- [x] Added `fingerprinting/workflow.py` for **one user prompt** → initial target reply → on-demand fingerprinting probes → pipeline → optional card and prior-model comparison; tests are synthetic and never use a user's key.
- [x] Updated root-level documentation and UI/backend contracts for prompt-only analysis and a separate secure user connection setup.

## P0 — Must finish before trusted live results

- [ ] **Confirm LoRA v2 label order** against the teammate's training notebook/checkpoint metadata. The checkpoint contains a `score.weight` matrix of shape `[5, 896]` but no mapping to five canonical LLM IDs. Current manifest uses a **provisional** mapping inherited from a different (1.5B) experiment, and the adapter deliberately suppresses named model candidates until this is confirmed. Compare actual model outputs on labeled known cases and update via a new release once confirmed. **Owner:** LoRA teammate. **Evidence:** signed label mapping and deterministic sample/score parity.
- [ ] **Pin actual LoRA base model revision.** The uploaded PEFT JSON identifies `Qwen/Qwen2.5-0.5B`, rank `16`, alpha `32`; it does not record the 40-character Hugging Face training commit. The v2 manifest temporarily uses `base_model_revision: main` for experimental loading. Replace with the training commit, freeze Python/Transformers/PEFT versions, and retest. **Owner:** LoRA teammate.
- [ ] **Run the actual LoRA v2 checkpoint.** The bundled tests validate weights, checksums and adapter wiring without loading Qwen weights. Install `requirements-lora.txt`, provision GPU/memory and the base model, run notebook-parity tests and publish a validation report. **Owner:** ML integration.
- [ ] **Calibrate LoRA unknown-model rejection.** Current `review_only` mode produces candidates only; held-out known/unknown model examples and per-class acceptance metrics are required before it can confirm identities. **Owner:** ML evaluation.
- [ ] **Calibrate Random Forest unknown-model rejection.** RF v1 is also review-only, so it cannot confirm final model changes. Train thresholds on validation data disjoint from the final holdout, measure unknown false acceptances and coverage. **Owner:** ML evaluation.
- [ ] **Validate live Harness judge calls** using an approved provider, API credentials from a server environment, and known/replayed probes. Mock judge is plumbing-only. Track privacy authorization, API cost, timeout, response repeatability and judge version. **Owner:** Harness/backend.
- [ ] **Integrate an authoritative model-card resolver.** `cards.enabled: false` remains the safe default. Implement `CardResolver.resolve()` for accepted canonical IDs, include source/version/domain, and handle missing/unknown cards. Existing Harness references/cards must be reconciled against your team's model-card storage. **Owner:** Cards/backend.
- [ ] **Define previous confirmed baseline history and change semantics.** A fresh prompt alone cannot reveal what *changed*. Store previous confirmed model ID, card snapshot, timestamp, deployment ID and card schema/version **outside** the inference package. The workflow returns `no_baseline`/`not_comparable` when data is missing. Reject unconfirmed candidates as baselines; approve comparisons only for same deployment/domain. **Owner:** Backend/product.
- [ ] **Implement authorized provider-specific `TargetClient` connections** that query the target model from the user's key and stored service/endpoint/model selection. The key cannot by itself determine which model to call. The initial user prompt and six Harness probes must run on the same authorized target deployment/session. **Owner:** Backend.

## P1 — UI/backend delivery

- [ ] **Build the production authenticated HTTP async-job service** implementing connection/job/cards/history routes in [`docs/BACKEND_INTEGRATION.md`](docs/BACKEND_INTEGRATION.md). Local mock jobs exist in M3, but the live provider path remains synchronous and neither route is production-ready. **Owner:** Backend.
- [ ] **Implement a single user API-key input workflow** (per-analysis ephemeral key first, optional saved personalization later): provider/endpoint/model selection, TLS, auth, no request/response logging of key material, secure worker handoff, quotas and allowlisting. The M1 mock endpoint deliberately REJECTS API-key fields. **Owner:** Backend/security.
- [ ] **Create the prompt-only UI** according to [`docs/UI_INTEGRATION.md`](docs/UI_INTEGRATION.md): one prompt box; connected AI indicator; optional advanced Stage 1 toggle; async progress; accepted vs candidate status; card and change diff only when backed by data. **Owner:** UI.
- [ ] **Extend M3 background processing to real provider jobs** for long probe/judge/model operations with timeouts, retries, rate/cost limits, cancellation, status polling/SSE, audit trail, error sanitization, private-data handling and user-scoped authorization. **Owner:** Backend/operations.
- [ ] **End-to-end test with a real user-authorized deployment:** send one prompt, receive initial reply, collect exactly required probes, run identity classification, resolve card and compare saved baseline. Test missing card, no baseline, invalid connection, wrong provider, rejected candidate, cost/timeout and unavailable judge. **Owner:** UI + backend + ML.

## P1 — Scientific validity and reproducibility

- [ ] **Create a common frozen held-out cohort** for all methods with prompt-group, persona, deployment, model-family and unknown-model splits; avoid leakage into LoRA training, RF training, Harness reference data or thresholds. Historical LoRA (67.6%) and RF (93.18%) results are not directly comparable.
- [ ] **Investigate Stage 1 false verifications:** a falsely accepted expected identity prevents Stage 2 from running. Report cross-family and within-family misses, not only overall accuracy. Stage 1 only recognizes four target IDs.
- [ ] **Assess RF shift and metadata leakage:** its 52-feature contract includes prompt ID, output tokens and latency, which may differ when a user queries the backend through another provider/runtime.
- [ ] **Freeze compatible inference environments:** Stage 1 `.joblib` files were saved with scikit-learn 1.6.1 while RF was rebuilt with 1.8.0. Validate compatibility or isolate runtimes, then record reproducibility hashes.
- [ ] **Validate full live LoRA → Harness → RF** after all blockers, with acceptance coverage, drift detection, unknown-model false acceptance, query cost and latency; don't interpret mock or review-only scores as real end-to-end identification accuracy.

## P2 — Further development

- [ ] **Onboard new models and datasets** (separate future milestone): model/catalog registration, cards, dataset validation, retraining, per-model RF OVR vs multiclass decisions, immutable artifact promotion and rollback.
- [ ] **Integrate CI and package publishing** with light tests by default, offline integration tests gated by artifact availability, and external API tests opt-in only. Decide whether large model files belong in Git LFS or artifact releases.

## Current status in one paragraph

The Stage 1, Harness and RF software adapters are integrated. LoRA **weights are now present and checksummed** as `lora/v2`, but class mapping, base training commit and inference parity remain unverified. All identity methods except the unvalidated live Harness judge currently lack an approved acceptance policy. A backend-neutral **prompt-first workflow**, synchronous mock/OpenAI-target HTTP endpoints, and **local SQLite-backed mock jobs** exist and are tested; **production auth/worker key handoff, real async jobs, card retrieval and historical change detection storage** must be built by the backend team. Until then, show `needs_review`, missing-card and no-baseline states honestly rather than claiming a verified model change.
