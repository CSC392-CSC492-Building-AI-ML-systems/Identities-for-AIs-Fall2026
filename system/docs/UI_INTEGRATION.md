# UI handoff — Prompt-only fingerprinting experience

**Updated November 18, 2026.** This document describes the **intended UI/HTTP contract**. The existing `system/` package provides a Python workflow but **does not implement HTTP routes or a deployed UI**.

## What the user sees

**One primary input: the prompt.** Users should not paste the model's reply, choose six probe prompts, or manually specify the predicted model. The user has already authorized a target AI connection using their API key or a supported integration. That account/connection setup is a separate secure flow; if no connection exists, first direct the user to connect one. A key alone cannot determine the provider, endpoint, or target deployment; the backend must know those separately.

1. User types one prompt and selects **Analyze**.
2. UI sends only `prompt_text` and the already authorized `connection_id` (if not implicit from their session) to backend.
3. Backend sends the prompt to the chosen target AI using the user's authorized connection; the AI's reply is the **initial fingerprint observation**.
4. Stage 2 runs by default: LoRA tries the initial reply → Harness, if reached, sends **six additional versioned probes** to that *same target AI* → Random Forest if necessary. Neither the replies nor probes need to be entered manually.
5. UI displays the outcome, the **model card if authoritative data is available**, and **changes since the last confirmed snapshot** if a baseline exists.

**Stage 1 remains OFF by default.** If exposed at all, put an opt-in in advanced settings, or have the backend enable it for an authorized comparison against a known previous/expected identity. Do not ask for a family identifier: the backend derives it from `system/catalog/models.json`.

## Recommended screen

- Prompt field, **Analyze** button, active AI connection status and, optionally, an advanced “Verify expected model first (Stage 1)” toggle.
- Progress: `queued` → `querying_initial_prompt` → `fingerprinting` (show methods when available) → `loading_model_card` → `completed` / `needs_review` / `failed`. Live probes and judge requests can take significant time and consume the user's API quota.
- Result: accepted model label, the deciding method, summary, model card (when available), model-change status, and field-level differences between the **current** and **previous** model cards if both are present.
- Diagnostics: show individual **candidate** predictions clearly labeled as *unconfirmed*. Show score types, probe count, stage1 enabled/skipped and runtime when useful. Never describe a max-softmax or RF vote as a validated probability of correctness.

### UI status rules

| Data field | Meaning and UI treatment |
|---|---|
| `fingerprint.final.status = identified` | An exact model identity was accepted; no previous model supplied. |
| `verified` | Accepted/verified identity matches a known expected baseline. |
| `drift_detected` | Accepted identity differs from supplied baseline; indicate **potential** model change, not independent proof. |
| `needs_review` | No method accepted an exact identity; any candidates are provisional. |
| `error` | Inference failed; do not claim identity or drift. |
| `model_card_status = available` | A genuine card has been retrieved and may be rendered. |
| `model_card_status = unavailable` | Identified model has no retrievable card; show "Model card unavailable". |
| `model_card_status = unconfirmed` | No accepted model; never attach a candidate's card as confirmed. |
| `change_status = no_baseline` | First run / no previous confirmed model; no comparison. |
| `same_model` / `model_changed` / `unresolved` | Compare accepted identity with persisted confirmed baseline; unresolved does not imply no change. |
| `card_comparison_status = not_comparable` | Current and prior authoritative card snapshots are not both available. |

## Proposed API contract (backend team must implement)

**1. User connects target AI once** (separate credentials flow; suggested `POST /api/v1/connections` or provider OAuth, not implemented). Backend creates a secure `connection_id` tied to the authenticated account, endpoint/provider/model routing and a secret vault reference. Do NOT embed the key in source, browser localStorage, job logs, result JSON, or analysis history.

**2. Submit a prompt:** `POST /api/v1/fingerprint/jobs`:

```json
{
  "prompt_text": "Explain recursion in Python.",
  "connection_id": "conn-authorized-123",
  "use_stage1": false,
  "domain": "risk"
}
```

`connection_id` may be omitted if the backend derives the active connection from the authenticated session. `use_stage1` and `domain` are optional advanced settings, not required form fields. **No `response_text`, model ID, probe answers, or API key are sent in the analysis request.**

**3. Return job handle:** `202 Accepted`, e.g. `{ "job_id": "job-123", "status": "queued" }`.

**4. Poll or subscribe:** `GET /api/v1/fingerprint/jobs/{job_id}` (or a server-sent events stream). Once complete, backend may expose the Python report in `result`:

```json
{
  "job_id": "job-123",
  "status": "completed",
  "result": {
    "request_id": "job-123",
    "target_queries": ["UI-INITIAL", "LM-01", "LM-05", "LM-06", "I1", "I2", "V1-15"],
    "model_card_status": "available",
    "model_card": {"model_id": "llama3.2-3b", "risk": "example value"},
    "change_status": "model_changed",
    "previous_model_id": "llama3.1-8b",
    "current_model_id": "llama3.2-3b",
    "card_comparison_status": "compared",
    "card_changes": [{"field": "risk", "before": "previous value", "after": "example value"}],
    "fingerprint": {
      "stage1_enabled": false,
      "stage1": {"verdict": "skipped"},
      "final": {"status": "drift_detected", "model_id": "llama3.2-3b", "resolved_by": "harness"}
    }
  }
}
```

This is **illustrative fake data**, not an actual Harness measurement or existing API response. Real `fingerprint` includes the complete `PipelineResult.to_dict()` fields and the exact probes actually executed; with Stage 1 off and no previous baseline, the status would be `identified` rather than `drift_detected`.

## Dependencies / UX constraints

- **Model card:** A successful fingerprint does not magically generate a card. Backend must map the accepted canonical identity to its authoritative card service and return a source/version. Cards are disabled in the default pipeline config until such a resolver is supplied. If unresolved, display an unconfirmed candidate separately and no authoritative card.
- **Changed information:** Requires previously saved confirmed identity and/or previous trusted card snapshot for the **same authenticated deployment**. Without baseline, show "First observation — no comparison available". When cards have different domain/schema versions, backend should not compute a misleading field-level diff.
- **API key:** The prompt screen asks only for the prompt **because connection setup happened earlier**. One-off keys require a separate secure connection step. The backend, not the frontend, executes API requests. Never forward the user's target key to an unrelated judge provider.
- **Provider identity is routing metadata**, not model-classifier ground truth. Do not send `provider_model_id` as the predicted identity to the system's Stage 2 methods.
- **Progress/error UX:** Allow cancellation, rate-limit and quota notices, provider failures, judge failures, missing cards and timeouts. A missing probe or API failure is not "no model change".

## Acceptance checklist for the UI team

- One prompt text field on analysis screen; no response field or manual probe editor.
- Connection indicator or separate connection setup for an absent key; no credential in results or browser storage.
- Stage 1 opt-in disabled by default; no family text field.
- Explicit separation of accepted identity vs unconfirmed candidate, card availability vs missing card, and model-change result vs no baseline.
- Asynchronous progress, cancelled/failed states, and truthful partial/unknown outcomes.
- UI understands that routes above are **not implemented** until the backend team ships them.
