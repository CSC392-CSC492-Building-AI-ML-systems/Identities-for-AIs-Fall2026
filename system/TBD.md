# Current update — root repository consolidation

- [x] Consolidate the root release into `system/`, `tests/`, `cards/` plus root README and ignore rules; move collector, research scripts, tests and fixtures; adjust card and onboarding paths and launcher. Preserve registered artifacts, catalog, configuration, backend and immutable raw data byte-for-byte. Remove old root legacy/ and 261 historical derived collector files from the distributed snapshot, retain deferred Stage 1 source and registered artifacts. No changes to the user's actual checkout. See `docs/REPOSITORY_CONSOLIDATION.md` and inventory.
- [x] Core suite: 373 tests passed; original root research tests: 14 passed. Collector dry run, real card family lookup, catalog audit, configuration and CPU Stage 2 replay passed. Real historical Stage 1 parity module is separate and was not rerun. No live judge/target calls or new model training.
- [ ] Next: frontend integration and end-to-end prototype demonstration using the review-only profile. Run authorized live target and judge tests, reconcile collector routes and card metadata, handle successful blank transport semantics, and validate candidate behavior. LoRA actual training/reload remains deferred until suitable compute; Stage 1, production authentication, thresholds and unknown-family detection remain deferred. No automated baseline promotion.

Older entries below are historical and paths may have changed.

---

# Current update — automated evaluation and reviewed publication

- [x] Add `release evaluate/evaluate-run/publish/rollback/history` using existing verified dataset snapshots, Factory and evaluator. Paired fixed-panel comparison, common label vs full cohort coverage, missing candidates count as failures, confusion matrices, hashes and review-only publication.
- [x] Add optional `training run --evaluate-candidates`: evaluate registered RF/LoRA candidates on validation; skip unchanged/unregistered methods; Harness requires explicit judge consent. No event scheduler or automatic activation.
- [x] Actual RF v2 vs v1 validation comparison: 49/51 vs 3/51; common five labels 15/15 vs 3/15. Different query budgets and legacy metadata mismatch; validation used for prompt selection, no independent holdout claim.
- [x] Verify local immutable review profile publication and rollback, preserve prior artifact versions; explicit worker restart selects chosen profile. 122 focused tests passed including temporary real RF training/evaluation.
- [ ] Real LoRA checkpoint/GPU or CPU validation and real judge/provider evaluation remain pending. Harness mock/partial evidence cannot publish; current release comparator fixed-panel only, independent/unseen-prompt and unknown-family evaluation still needed.
- [ ] Optional reviewed dataset trigger / CI; no automatic test tuning or automatic publication. Final repository consolidation (`system/`, `tests/`, `cards/`) and frontend integration/prototype demonstration next. Audit legacy dependencies before removing, preserve raw and active artifacts/fixtures. Stage 1, production auth, thresholds deferred.

Older entries below are historical; this update takes precedence.

---

# Current update — model and family onboarding

- [x] Add canonical identity onboarding (`onboard-model plan/register/draft-cards/publish-cards/status`), explicit new-family permission, disabled collector entry, draft isolation, existing card checker and family aggregation reuse, declared Stage 2 artifact coverage.
- [x] Audit supplied sibling snapshot: 17 identities / six families; nine matching collector routes, six missing, two placeholder mismatches; 44 existing domain cards lack researched_by and 24 are absent. No existing card or route was rewritten.
- [x] Validate temporary seventh-family registration, raw dataset eligibility, unchanged old panel, draft gate and real card library family lookup. 108 focused tests passed; no actual new model registered in shipped catalog.
- [ ] Reconcile root collector routes against verified IDs; fill actual researcher provenance and missing domain cards/licences. User/team must confirm sources and permissions. Existing root card library can still expose historical incomplete cards; audit and correct them separately.
- [ ] Model collection and retraining: collect comparable probes/personas for old + new identities, register approved dataset/split, run RF/Harness and LoRA when compute available; evaluate and review candidates. New transports require explicit implementation.
- [ ] Automated evaluation/publication and optional dataset-approval trigger; then consolidate repository layout and complete frontend prototype demonstration.
- [ ] Live provider/judge validation, explicit successful blank semantics, LoRA real checkpoint and arbitrary-prompt evaluation pending. Stage 1, production auth, confidence thresholds and unknown-family detection deferred.

Older entries below are historical; this update takes precedence.

---

# Current update — Stage 2 review-only live integration

- [x] Add separate opt-in `live_stage2_review` API/queue mode, config-driven Factory worker, Harness v2 with deterministic abstaining mock judge, real RF v2, six-probe shared cache, explicit LoRA unavailable state, typed candidate results and agreement; Stage 1 stays off.
- [x] Add separately consented optional external judge route using trusted Harness config and worker-only credential. Unconfigured consent fails before target calls. Actual live judge/provider testing remains pending.
- [x] CPU replay of actual stored probe trace through RF v2; new backend tests, OpenAPI, PowerShell demo guide. See `docs/BACKEND_STAGE2_REVIEW.md`.
- [ ] LoRA operational validation: CPU smoke or remote GPU (no local NVIDIA required); actual fine-tuning, checkpoint reload, pinned revision, class mapping and held-out evaluation. Then configure the new artifact in the live profile.
- [ ] Run authorized real target and judge smoke tests, handle explicit live blank/refusal semantics, confirm judge model availability and dependencies, validate costs and error paths. Prototype remains localhost-only.
- [ ] Model/family onboarding, automatic publication/evaluation and repository consolidation. No new removals.
- [ ] Stage 1, production authentication, calibrated acceptance/unknown-family detection remain deferred. No confirmed automatic identity or baseline promotion.

Older entries below are historical; current status takes precedence.

---

# Current update — Harness reference builder; Stage 1 deferred

- [x] Implement and register `harness/v2` from the approved fixed panel: 17 models, 816 training-only reference records, 28 blanks; no new card snapshot, no fitted weights, no judge calls during build.
- [x] Support exact reference-content reuse (`skipped_unchanged`), catalog-driven identities, successful blank observations, review-only acceptance, and bounded replay tool.
- [x] Defer Stage 1 training and keep it OFF in all new prototype configs. Preserve historical code/artifacts and tests; do not schedule its implementation before Stage 2 is functional.
- [ ] Run controlled real Harness judge replay and evaluate candidate accuracy; three-case mock validation passed, full 51-case mock replay timed out; no accuracy claim.
- [ ] Run LoRA GPU smoke test using pinned base revision and evaluate the trained artifact.
- [ ] Connect live HTTP worker to config-driven LoRA → Harness → RF (Stage 1 off), add real judge and authoritative card retrieval only for approved identities; retain conservative review-only behavior pending acceptance validation.
- [ ] Model and family onboarding, evaluation/publication and repository consolidation (no further unapproved removals).
- [ ] Production authentication and confidence threshold / unknown-family calibration deferred for the prototype.

Older entries below document prior milestones and may contain superseded status descriptions.

---

# Automated LoRA training — November 26, 2026 (current)

- [x] Implement notebook-derived LoRA strategy in existing orchestrator, shared blank preprocessing, balanced class/prompt data, pinned split provenance, sorted label mapping, manifest and validation output, optional candidate registration.
- [x] Preview actual six-probe dataset: 1,224 train / 306 validation rows, 17 identities, 42 / 17 blanks. Add separate frozen test evaluation using existing Factory. Synthetic lifecycle tests only; no actual HF training.
- [ ] Supply actual 40-character base commit, run GPU smoke and full training, validate exported head/reload parity, freeze dependencies and evaluate candidate. Existing v2 remains provisional. New candidate remains review-only.
- [ ] Broader common prompt coverage and independent persona/prompt/unknown-family evaluation. Fixed six-probe response-level results are not equivalent to multi-query RF trace-level results. Live arbitrary prompts require separate evaluation.
- [ ] Harness reference builder, Stage 1 training, live worker integration, model/family onboarding, CI and repository consolidation. No additional deletion. Production authentication and confidence thresholds deferred.

---

# Multi-probe RF and teammate intake — November 26, 2026 (current)

- [x] Reviewed three teammate repositories; LoRA source-only notebooks extracted, no new checkpoint; Agentic runtime and cards match existing pinned Harness v1, no duplicated runtime. See `docs/TEAM_BRANCH_REVIEW.md`.
- [x] Registered Agentic raw snapshot (17 identities), complete six-probe fixed panel; explicit disjoint-persona split, blanks retained, failed retries excluded. Old dataset/version kept.
- [x] Implemented automatic RF training in orchestrator, validation-only greedy probe selection, shared text-only multi-probe feature ABI, review-only Factory adapter and separate held-out evaluation. Five-probe v2 registered but not activated. Test 94/102 candidates; see `docs/RF_MULTI_PROMPT.md`.
- [ ] Collect wider balanced prompt pool and additional persona/configuration groups; independently evaluate unknown families, same-family mistakes and generalization. No calibrated thresholds yet. Do not select on test.
- [ ] LoRA: convert supplied notebook recipe to automated training strategy, pin base revision, confirm checkpoint mapping, implement blank parity, export actual weights; Harness: reference-builder with known-set update, data partitions, card mappings, blank policy and actual judge validation. Both not yet integrated as trainers.
- [ ] Prototype live worker still uses mock Harness only; connect config-driven classifiers including multi-probe RF, provide explicit completed-blank semantics from live providers, verify reused probe cache and actual live end-to-end. No production authentication or threshold work activated.
- [ ] Review overlaps (246 RF test rows in pinned Harness references), privacy/licence and new dataset storage before publishing. Maintain separate known-prompt/persona protocol versus general unseen-prompt protocol. No additional cleanup performed.

---

# Training orchestration foundation — November 26, 2026 (current status)

- [x] Refine onboarding: blank no-error responses retained, recorded errors excluded; old split policy remains reproducible. New example split has 9,634 eligible rows, 83 excluded; 17 model IDs in every eligible partition. New test still overlaps Harness v1 by 270 record IDs.
- [x] Add `inspect` and optional verified local split hash binding to classifier templates/provenance. Existing artifact manifests unchanged.
- [x] Implement local training plan/run/history, one method or batch, pinned data/split provenance, input-integrity checks, candidate validation/optional registration, no automatic activation. All four actual trainer implementations remain unavailable; synthetic tests only.
- [ ] Integrate RF trainer from finalized code (feature ABI, null/blank handling, parity and validation).
- [ ] Implement Harness reference builder with separate complete probe/session protocol and skip refresh when data is unchanged; validate actual judge.
- [ ] Integrate LoRA trainer (pinned base revision, labels, preprocessing, GPU/dependencies) and generalize Stage 1 training/adapter when team specifications arrive.
- [ ] Add automatic run trigger after reviewed data approval, relevant-data change detection, reproducible run environments, unified validation/test execution, publication/rollback, and CI. Current explicit batch command is not an event scheduler.
- [ ] **Legacy cleanup:** apply checked Jev removal to real repo; review active research uses before applying four derived-data groups; keep all raw, pinned artifact dependencies and test fixtures. See `docs/LEGACY_CLEANUP.md`. Future folder migration into system/tests/cards still pending.
- [ ] Model/family onboarding using authoritative sibling cards/catalog and collector; no further unapproved removals.
- [ ] Prototype demo: wire real selected artifacts and judge to the live worker and run end-to-end inference/evaluation. Do not promote unconfirmed identities. Production authentication, operational hardening and threshold calibration deferred; local-only demo.

Older milestone notes below are historical; the current entries supersede conflicting eligibility, cleanup and training status statements.

---

# Dataset onboarding — prototype (November 26, 2026)

- [x] Add offline validate/register/split/audit/export CLI; immutable raw files,
  canonical IDs, SHA-256 manifests, duplicate/error/blank diagnostics, deterministic
  prompt-group allocations, coverage checks and record-reference splits.
- [x] Test on the existing 20 files (9,717 records); 8,869 structurally eligible,
  848 excluded. Preserve raw manifest and all raw bytes. Generate an illustrative
  four-way split and audit overlap with pinned Harness v1.
- [ ] ML team: reconcile actual prompt definitions/aliases, historical training and
  reference overlap (795 shared record IDs with Harness v1; 393 in candidate test),
  paired probe completeness, rare-class coverage and unknown-family cohorts before
  treating a split as an independent benchmark. Candidate splits are not approved.
- [ ] Review privacy/licensing and decide retention/storage before publishing raw data.
- [ ] Extend classifier provenance verification to exact split membership and
  split/export hashes; automatic training and artifact promotion remain deferred.
- [ ] Model and family card onboarding, real inference integration and CI remain
  open. Production authentication and confidence calibration deferred by team choice.
  No further legacy cleanup approved.

---

# Classifier onboarding — prototype (November 26, 2026)

- [x] Add manifest templates, full payload inventory/checksums, canonical model IDs,
  provenance validation and adapter-specific static checks using the current registry.
- [x] Register trusted candidates under new artifact IDs; create separate evaluation YAML,
  preserve existing artifacts and production config. No further legacy cleanup.
- [ ] Obtain actual retrained bundles and their dataset/split manifests, code revisions,
  dependency versions and evaluation evidence; run real parity/holdout evaluations.
- [ ] Upgrade Stage 1 adapter for the intended six families (currently four Gemini/Llama
  identities); upgrade RF/LoRA/Harness adapters when submitted contracts change.
- [ ] Integrate approved real config-driven classifiers into the live backend worker.
  Current worker is Harness-only with mock judge; registering new weights does not
  change that behavior. Authentication expansion deferred for prototype.
- [ ] Confidence/unknown-family acceptance calibration deferred, not solved by onboarding.
  New LoRA and RF candidates must be review-only. No automatic activation or baseline promotion.
- [ ] Model/catalog + card onboarding and automated retraining remain separate future
  work. Dataset ingestion/split tooling is now implemented below. Local dataset hash
  check is not proof of split membership.
- [ ] Team review before loading joblib or executing submitted Harness sources. Local tool
  does not provide a sandbox, signature verification, or crash-safe distributed publishing.

---

# Dataset update — November 26, 2026

- [x] Stage the exact new `raw.zip` as `datasets/collector_raw/2026-11-26/`, preserving bytes and providing file checksums and record counts. All 17 IDs already exist in the catalog.
- [ ] **ML team:** Review 83 collection errors and 765 blank responses without recorded errors (631 in Qwen3.5 9B fingerprint data); define preprocessing and observable-response handling. Confirm missing Gemini 3.1 Pro `fingerprint_v0` and completeness of paired probe sessions.
- [ ] Freeze leakage-checked train/calibration/test cohorts, prompt/persona definitions, licenses and provenance; do not automatically merge raw data into historical evaluation or Harness references.
- [ ] Publish new trained artifacts and Harness reference versions with checksums, label/feature contracts, dataset manifest hash, calibrated unknown rejection, and regression reports before switching configuration. Existing artifacts remain unchanged.
- [ ] Review dataset privacy and redistribution rights before committing raw records to GitHub; decide appropriate data storage.

---

# M6 — Deployment-linked jobs (November 25, 2026)

- [x] Owner-validate an optional `deployment_id` on live job submission; resolve routing target from the reviewed deployment, reject conflicting target metadata, and return 404 for cross-user access.
- [x] Pin the reviewed baseline **revision at submission time** and store the associated reference with the encrypted job; no automatic promotion of candidates.
- [x] Add `GET /api/v1/deployments/{id}/jobs` and a typed `result.ui_result` response with conservative identification/card/change states.
- [x] Add additive SQLite migration and tests covering old unlinked jobs, reviewer changes during queueing, fake target calls, and owner isolation.
- [ ] **Backend M7:** Use vetted production authentication, managed secrets/credentials, data privacy and user quota policies before remote frontend launch. Saved personalization API keys are not implemented.
- [ ] **ML/backend:** After ML approval, introduce accepted identities into the UI summary with validated open-set rejection; never auto-promote a candidate into reviewed baseline history.
- [ ] **Stage 1 live jobs:** Support optional verification with a known supported baseline ID (currently HTTP 409 even for linked jobs).
- [ ] **Deployment connection setup:** Create durable, authenticated connection metadata and safe per-job key retrieval or delegated credentials; the current UI submits a key for each job.
- [ ] **Operations:** Add robust migrations, cancellations, timeouts/heartbeats, retention, rate limits, and card lookup for accepted current identities.

---

# Backend Milestone 4 — implemented, LOCAL ONLY (November 19, 2026)

- [x] Implement local high-entropy bearer token authentication for live jobs; user ID derived server-side, authenticated job ownership enforced; only token SHA-256 digests stored in `.local/dev_users.json`.
- [x] Implement separate authenticated `POST/GET /api/v1/fingerprint/live-jobs` and a separate worker `--kind live`; original mock jobs remain for offline learning.
- [x] Keep the per-analysis OpenAI key **out of SQLite**: a temporary Fernet-encrypted local vault file, deleted on normal success/failure, with expiry cleanup. Encrypt queued prompt/metadata and completed result in SQLite.
- [x] Disable the unauthenticated legacy synchronous live endpoint by default; opt-in flag only for localhost learning.
- [x] Add isolated fake-provider tests for 7 target requests, cross-user access, privacy, expiry, worker error handling, concurrent claims and process isolation. **Evidence:** `tests/test_backend_live_jobs.py`, `docs/BACKEND_MILESTONE4.md`.
- [ ] **Production identity and transport:** Replace dev bearer tokens with a trusted account/OIDC service, TLS, audit logs, rate limiting, token revocation/expiry, ownership checks for all routes, tenant isolation and restrictive CORS.
- [ ] **Managed key/secret infrastructure:** Local `.local/dev_job.key` coexists with encrypted data and is NOT a production protection boundary. Replace with managed secrets/KMS, separate keys and rotation, secure storage permissions and background TTL cleanup.
- [ ] **Worker robustness:** Implement leases/heartbeats, stuck-worker recovery, cancellation, a privacy retention policy, idempotency controls and provider cost ceilings. Current stale expiry may mark very slow but legitimate jobs abandoned; do not retry billable requests automatically.
- [ ] **Real provider smoke test:** No genuine billable OpenAI calls made in automated tests; confirm model routing, timeouts and seven-query behavior with a test account before deploying.
- [ ] **Real Harness judge and approved acceptance policies:** Still mocked in backend; no verified model identity, trusted model card or change declaration yet.

---

## Backend Milestone 2 — next work and known limitations

- [x] Add local, per-analysis OpenAI Responses API **target** adapter: fixed HTTPS endpoint, safe key handling in memory, bounded output, no retries, sanitized errors and fake-provider tests. See `docs/BACKEND_MILESTONE2.md`. This is not production authentication.
- [ ] Run a controlled **real** OpenAI target API smoke test with a development key and a supported API model; verify seven provider calls, measured latency, token cost and source output. No paid/API calls were made during automated tests.
- [ ] Design and implement authenticated users and per-user authorization before hosting the API publicly. Use HTTPS end-to-end, redacted request logging, quotas/rate limits, CSRF strategy (for any cookie sessions), and narrow CORS policy.
- [ ] Design a safe strategy for keys entered in personalization: server-side encryption/managed secrets, access controls, key rotation and deletion; avoid persistent browser localStorage. The current `/analyze/live` keeps keys only for its synchronous request.
- [ ] Move synchronous analyses to durable jobs/workers before live multi-user operation: bounded probe budgets, retry/cancellation policy, provider errors and auditability without storing secret contents.
- [ ] Add further providers only after the first one is verified. Provider and target deployment must be selected for API routing, never treated as ground truth for classification.
- [ ] Integrate real judge under explicit data-transfer consent. Current live route uses **mock judge** and cannot claim a confirmed fingerprint or validated card/change comparison.

# TBD — Release blockers and integration work

**Last updated: November 19, 2026 — Backend M4.** This is the active backlog for the `system/` GitHub subdirectory. Keep this file updated with owner, date, validation evidence and published artifact IDs. Previous milestone backlog is archived in [`docs/IMPLEMENTATION_TBD_HISTORY.md`](docs/IMPLEMENTATION_TBD_HISTORY.md). **Do not place credentials or private responses in Git.**

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

## Backend Milestone 5 — cards/history integration (Nov 19, 2026)

- [x] Add owner-scoped SQLite monitored deployments and **append-only manually reviewed** baseline history, storing full card snapshots and deterministic SHA-256 digests. Tests: `tests/test_backend_history.py`.
- [x] Expose the team's **existing root `cards/cardlib.py`** through authenticated read-only HTTP without copying/redefining the card data. Cards remain `unavailable` when the sibling repository `cards/` folder isn't present.
- [x] Compare two latest reviewed baseline identities and card snapshots, field by domain/field ID, and derive within-family versus cross-family changes using the canonical catalog.
- [x] Add `system/CLEANUP_REVIEW.md` with **no removals performed**, listing each proposed cleanup, its purpose, overlap evidence, and required owner approval.
- [ ] Link authorized live analysis jobs to a monitored deployment, validate provider/routing identity, and carry the prior approved baseline to workers when Stage 1 is explicitly enabled. Current M4 worker still refuses Stage 1.
- [ ] Allow only independently verified, validated accepted ML results to propose review of a new baseline. **Never auto-promote** `needs_review`, closed-set candidates, or mock-judge outputs.
- [ ] Build production-grade authenticated user management and encrypted history persistence with retention/deletion rules and audit logs. M5 SQLite history contains plaintext card snapshots, routing metadata, deployment labels and notes; local-only.
- [ ] Integrate a real Harness judge, calibrated LoRA/RF rejection policies, and unknown-family detection before claiming the end-to-end pipeline can confirm model swaps.
- [ ] Get explicit per-item approval before cleanup actions in `CLEANUP_REVIEW.md`; the out-of-date uploaded `system/` folder was ignored as requested.

## Approved cleanup status — November 22, 2026

- [x] **C1 Stage 1 research-script deduplication:** Removed only the 17 byte-identical `system/reference_stage1/scripts/*.py` copies. Retained original repository-root `scripts/*.py`, all Stage 1 classifiers, thresholds, versioned artifact manifests, and the opt-in Stage 1 feature. Updated original-script parity test to use root scripts when present. After overlay extraction, run the checked `system/tools/apply_c1_cleanup.py --apply` migration to remove stale copies from your working tree. Historical release-manifest provenance is intentionally unmodified; see `docs/CLEANUP_C1_MIGRATION.md`.
- [ ] **C2–C8 remain unapproved and unchanged.** Do not delete Harness card snapshots, research tests, Jev code, requirements, card tools, collector, or legacy HTTP endpoints without new, separate approval.
