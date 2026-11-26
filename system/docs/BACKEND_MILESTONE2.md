# Backend Milestone 2 — OpenAI target integration (local development)

**Status:** Implementation and offline tests complete; no live OpenAI API request or real identification accuracy has been verified. **This is NOT a production service.**

Milestone 2 adds a real provider-target adapter without replacing the Milestone 1 mock route. The app connects to the official [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create) over HTTPS using `httpx`. It accepts one user prompt, an OpenAI model *routing ID*, and a per-analysis API key, then sends the initial prompt plus the six versioned Harness probes using the same key and target model. **The Harness judge remains MOCKED and must never confirm model identity.** Stage 1 remains OFF and has no confirmed-baseline storage.

## Files and responsibilities

| File | Purpose |
|---|---|
| `backend/providers/openai.py` | Fixed OpenAI HTTPS Responses endpoint, header authentication, bounded output, `store=false`, safe error mapping and text extraction |
| `backend/services/live.py` | Request-scoped provider constructor, reused target client for initial and six probe queries, resource cleanup |
| `backend/schemas.py` | Strict `LiveOpenAIAnalyzeRequest` with `SecretStr` for key; response explicitly `mode=live_target_mock_judge` |
| `backend/app.py` | New `POST /api/v1/analyze/live`, dependency injection and redacted errors; original mock route remains unchanged |
| `backend/dependencies.py` | Inject independently testable mock and live gateways |
| `backend/dev_live_client.py` | Optional local CLI client that prompts for API key without putting it in shell history or command arguments |
| `tests/test_backend_openai_live.py` | Offline `httpx.MockTransport` and FastAPI tests; **no actual provider calls or real keys** |
| `requirements-backend.txt` | Uses `fastapi`, `uvicorn`, `httpx`, `pydantic`; no separate SDK required |
| `TBD.md` | Auth, persistence, asynchronous jobs, real judge and model acceptance blockers |

## Windows Git Bash — install and start from GitHub root

First install Python 3.11 (if needed) and open a fresh Git Bash terminal. The checked-in reconstructed Random Forest requires scikit-learn 1.8.0, which requires Python >=3.11.

```bash
py -3.11 -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r system/requirements-integrated.txt
python -m pip install -r system/requirements-backend.txt
python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

If `.venv` already exists with Python 3.11+, simply activate it. Open `http://127.0.0.1:8000/docs` (Swagger UI). `/health` and `/api/v1/capabilities` also work without a key.

### Safe offline route (no API cost)

Use `POST /api/v1/analyze` with `{ "prompt_text": "Explain recursion in Python." }`. This returns `mode=mock`, a synthetic initial response and six synthetic Harness probe responses.

### Opt-in live OpenAI **target** route (billable)

**For local use only**: `POST /api/v1/analyze/live` with a JSON request equivalent to:

```json
{
  "prompt_text": "Explain recursion in Python.",
  "provider": "openai",
  "target_model": "YOUR_ACCESSIBLE_OPENAI_MODEL_ID",
  "api_key": "PASTE_YOUR_KEY_ONLY_IN_THE_LOCAL_UI",
  "use_stage1": false
}
```

Do not paste a real key into GitHub, a shell command, logs, screenshots, committed `.env`, URLs, or a shared instance of Swagger. Instead, you can enter it into the **local** Swagger request body, or use the interactive CLI from a second Git Bash window (a key prompt that doesn't echo input):

```bash
source .venv/Scripts/activate
python -m system.backend.dev_live_client \
  --model YOUR_ACCESSIBLE_OPENAI_MODEL_ID \
  --prompt 'Explain recursion in Python.'
```

The `target_model` is necessary for OpenAI to route the request, **not** ground truth passed to the fingerprinting classifier. In the eventual UI, this identifier and API credential are configured in personalization/connection settings; the **analysis screen itself still contains only the prompt**.

The response includes `mode=live_target_mock_judge`, `status=needs_review`, `model_id=null`, `stage1_enabled=false`, and `target_queries` listing requested probes (`UI-INITIAL`, `LM-01`, `LM-05`, `LM-06`, `I1`, `I2`, `V1-15`). If the upstream API rejects the key, model, prompt, or request budget, a sanitized 502/429/504 error may be returned. Any per-probe failure may appear as a non-accepted method outcome; never interpret it as model identification.

## Important security and API boundaries

- The live route accepts one API key **per analysis** as `SecretStr` and uses it to send the first question and up to six additional probes. It never records the key in model results, metrics, dataset outputs, a database, or app global state. The key necessarily resides in process memory during the request; Python cannot guarantee secure immediate erasure.
- The user must trust the backend hosting the route. **Do not expose this development service publicly**: no user authentication, HTTPS termination, rate limits, durable jobs or persistent secret storage exist. For deployment, implement authenticated jobs over HTTPS, authorization and rate limiting first; a password/secret vault is needed for optional saved personalization keys.
- Target API calls use `https://api.openai.com/v1/responses` exclusively. Clients cannot override the destination, and redirects are not followed. JSON requests set `store=false`, `max_output_tokens=512`, `timeout=25 seconds`, no automatic retries. This is a bounded *per-call output* limit, not a total monetary budget. Seven calls can still incur nontrivial charges; set overall quotas and cancel/retry policy before exposing to users.
- Any provider, transport, and validation errors returned through HTTP are sanitized; API keys are not included in request paths, error details, or response metadata. We do not claim immunity to reverse-proxy body logging or host-side inspection; that is a deployment responsibility.
- The live request's provider key is **not** used for a Harness judge model. The judge is offline and mocked. Real judging later requires separate service credentials and explicit user consent/data-transfer rules.
- No real LoRA v2/RF acceptance or model-card resolver is activated in this milestone. The response must not claim verified model identity, model cards or change history.

## Run tests

```bash
# Fast backend tests
python -m unittest system.tests.test_backend_api system.tests.test_backend_openai_live -v
# Full system suite (some legacy Stage 1 tests are slow)
python system/run.py test
```

Offline tests use `httpx.MockTransport` and injected fake target providers, verify the actual OpenAI request schema, per-request credential isolation, seven-query integration, non-disclosure in errors, and Stage 1 opt-in restrictions.

## Next milestone

Implement authenticated background jobs and a durable data store, then optionally save user credentials using an approved secret manager. Only after those are designed should a public UI submit keys. Separately, validate real Harness judging, LoRA label mapping/inference, confidence/rejection and card/history sources before marking results confirmed.
