# Frontend handoff — Milestone 6 API contract

**Current implemented local-development API.** For full setup and security restrictions see [`BACKEND_MILESTONE6.md`](BACKEND_MILESTONE6.md). For machine-readable types see [`OPENAPI_M6.json`](OPENAPI_M6.json).

**Base URL for local dev:** `http://127.0.0.1:8000`. Use `Authorization: Bearer <local-development-token>` for deployments, cards, and live jobs. **Do not deploy this API publicly** without a production authentication, HTTPS and secrets review.

## Main screens and endpoints

| UI screen | Method | Route | Status |
|---|---|---|---|
| Health | GET | `/health` | Implemented, no auth |
| Feature flags | GET | `/api/v1/capabilities` | Implemented, no auth |
| Deployments | POST | `/api/v1/deployments` | Implemented, bearer |
| Deployments | GET | `/api/v1/deployments` | Implemented, bearer |
| Deployment detail | GET | `/api/v1/deployments/{id}` | Implemented, bearer |
| Manually reviewed baseline | POST | `/api/v1/deployments/{id}/baselines` | Implemented, bearer |
| Reviewed identity history | GET | `/api/v1/deployments/{id}/history` | Implemented, bearer |
| Reviewed card/identity changes | GET | `/api/v1/deployments/{id}/changes` | Implemented, bearer |
| Analysis list per deployment | GET | `/api/v1/deployments/{id}/jobs` | **New M6**, bearer |
| Submit live analysis | POST | `/api/v1/fingerprint/live-jobs` | Implemented, bearer |
| Poll live analysis | GET | `/api/v1/fingerprint/live-jobs/{job_id}` | Implemented, bearer |
| Authoritative catalog card | GET | `/api/v1/models/{model_id}/card` | Implemented, bearer; may be unavailable |

Legacy mock/synchronous routes remain in the repository for local regression tests. Do **not** build the production frontend against those routes.

## Prompt-first UX

The main analysis screen needs **one prompt input** and a selected existing deployment (or explicit target routing ID when no deployment is registered). The API key is not saved in Milestone 6: collect it through a separate ephemeral connection/key dialog, not a form field in the main prompt itself. Never put the API key in query parameters, browser storage, error logs, or job results.

When a deployment is selected, submit:

```json
{
  "prompt_text": "Explain recursion in Python.",
  "provider": "openai",
  "deployment_id": "selected-owned-deployment-id",
  "api_key": "ephemeral-user-key",
  "use_stage1": false
}
```

`target_model` can be omitted here because the backend retrieves the saved deployment routing ID. For an unlinked job use `target_model` instead of `deployment_id`. Live `use_stage1: true` still returns HTTP 409 even if the deployment has a baseline. No other providers are yet implemented for live requests.

The submit route returns HTTP 202 `{job_id, status: "queued", mode, created_at, deployment_id, baseline_revision}`. Poll the job GET route until `status` is `completed` or `failed`. The HTTP 200 poll envelope contains `job_id`, `status`, `mode`, timestamps, `deployment_id`, `baseline_revision`, `error_code`, `result`. While queued/running, `result` is `null`. On failure, `result` is `null` and `error_code` is an approved generic string (never raw provider errors).

For a completed job, render **`result.ui_result`**, not internal `result.report`:

| UI field | Current possible value | Meaning |
|---|---|---|
| `identification.status` | `needs_review` | No validated accepted identity |
| `identification.accepted_model_id` | `null` | Never infer identity from routing target |
| `identification.reason` | `live_judge_not_validated` | Harness judge is mock |
| `comparison.status` | `no_baseline` | Deployment has no reviewed history, or job unlinked |
| `comparison.status` | `insufficient_evidence` | Baseline exists but latest identity cannot be accepted |
| `comparison.previous_model_id` | confirmed model ID or `null` | Previous **reviewed** identity only |
| `comparison.current_model_id` | `null` | No confirmed new identity |
| `comparison.identity_change` | `null` | Unknown, not false |
| `comparison.family_change` | `null` | Unknown, not false |
| `comparison.card_comparison.status` | `not_comparable` | Cannot diff an unconfirmed current card |
| `model_card.status` | `unavailable` | No confirmed new model card to show |
| `baseline` | snapshot reference or `null` | Pinned at submission, unaffected by later history changes |
| `evidence.identity_confirmed` | `false` | Explicit guard against overstating results |

**Do not show “No change” when `identity_change` is `null`.** Display “Not enough evidence to determine whether the deployment changed.”

The reviewed-history `/changes` route compares *two manually reviewed* baseline snapshots and is independent of the current analysis job.

## Auth, permissions, validation

- 401: bearer token missing or invalid. 404: nonexistent or other-user deployment/job. 409: incompatible routing ID or live Stage 1 opt-in. 422: invalid request fields. 503: live-job worker encryption/auth configuration unavailable.
- Never tell an unauthorized user whether another user's deployment exists. Do not show an API key in UI history.
- The system currently lacks production login, secure saved-key personalization, cancellation, progress-per-probe, and automatic promotion of model identities.
- An API key alone cannot choose a model; the deployment (or `target_model`) is used to route requests and **never counts as fingerprint ground truth**.

## Example integration sequence

1. Fetch `GET /api/v1/deployments` and select or create one.
2. Optionally display its latest reviewed baseline from `GET /api/v1/deployments/{id}`.
3. Collect a prompt and ephemeral API key; send the POST with `deployment_id`.
4. Poll `GET /api/v1/fingerprint/live-jobs/{job_id}`; show generic progress.
5. Render `result.ui_result` with explicit review/unknown states.
6. For reviewed historical changes, use `GET /api/v1/deployments/{id}/changes`.
7. For a supported, manually confirmed model ID, use `GET /api/v1/models/{model_id}/card`, but never label a card as belonging to the current live target unless identity has actually been confirmed.
