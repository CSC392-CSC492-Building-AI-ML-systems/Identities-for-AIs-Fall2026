# TBD — Release blockers and integration work

**Last updated: November 18, 2026.** This is the active backlog for the `system/` GitHub subdirectory. Keep this file updated with owner, date, validation evidence and published artifact IDs. Previous milestone backlog is archived in [`docs/IMPLEMENTATION_TBD_HISTORY.md`](docs/IMPLEMENTATION_TBD_HISTORY.md). **Do not place credentials or private responses in Git.**

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

- [ ] **Build an HTTP async-job service** implementing proposed connection/job/capabilities/cards/history routes in [`docs/BACKEND_INTEGRATION.md`](docs/BACKEND_INTEGRATION.md). There is no HTTP server in `system/`. **Owner:** Backend.
- [ ] **Build secure user key onboarding** (OAuth or separate TLS-secured key enrollment, vault/session binding, auth and quotas). The main analysis UI asks only for a prompt *after* connection setup. Do not echo/commit keys or allow arbitrary URLs/SSRF. **Owner:** Backend/security.
- [ ] **Create the prompt-only UI** according to [`docs/UI_INTEGRATION.md`](docs/UI_INTEGRATION.md): one prompt box; connected AI indicator; optional advanced Stage 1 toggle; async progress; accepted vs candidate status; card and change diff only when backed by data. **Owner:** UI.
- [ ] **Add background processing** for long probe/judge/model operations with timeouts, retries, rate/cost limits, cancellation, status polling/SSE, audit trail, error sanitization, private-data handling and user-scoped authorization. **Owner:** Backend/operations.
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

The Stage 1, Harness and RF software adapters are integrated. LoRA **weights are now present and checksummed** as `lora/v2`, but class mapping, base training commit and inference parity remain unverified. All identity methods except the unvalidated live Harness judge currently lack an approved acceptance policy. A backend-neutral **prompt-first workflow** exists and is synthetically tested; **provider key management, HTTP endpoints, card retrieval and historical change detection storage** must be built by the backend team. Until then, show `needs_review`, missing-card and no-baseline states honestly rather than claiming a verified model change.
