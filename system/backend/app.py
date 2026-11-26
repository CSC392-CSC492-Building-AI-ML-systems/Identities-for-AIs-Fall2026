"""FastAPI Milestone 6: deployment-linked authenticated live jobs, plus local mocks.

From the repository root:
    python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload

This is still a localhost development application. Linked live jobs require
bearer auth, encrypted queued inputs/results and a separate encrypted credential
vault. Production OIDC, managed secret storage, HTTPS, rate limits and consent
are NOT implemented.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .dependencies import get_analysis_gateway, get_live_analysis_gateway
from .schemas import (
    AnalyzeRequest, AnalyzeResponse, LiveOpenAIAnalyzeRequest,
    LiveOpenAIAnalyzeResponse, CapabilitiesResponse, HealthResponse,
    CreateMockJobRequest, CreateJobResponse, JobStatusResponse,
    CreateLiveJobRequest, CreateLiveJobResponse, LiveJobStatusResponse, DeploymentJobsResponse
)
from .services.analysis import BaselineRequiredError, MockAnalysisGateway, make_mock_gateway
from .services.live import LiveOpenAIAnalysisGateway
from .providers.openai import ProviderRequestError
from .jobs.store import SqliteJobStore
from .jobs.live_store import SqliteLiveJobStore
from .security.auth import LocalTokenAuth, default_auth, require_user
from .security.crypto import FileSecretVault, LiveCrypto
from .history_store import HistoryStore, NotFound
from .cards_repository import RepositoryCards
from .history_api import router as history_router
from ..fingerprinting.model_catalog import ModelCatalog
from pathlib import Path
from uuid import uuid4
import os


def create_app(gateway: MockAnalysisGateway | None = None,
               live_gateway: LiveOpenAIAnalysisGateway | None = None,
               job_store: SqliteJobStore | None = None, *,
               token_auth: LocalTokenAuth | None = None,
               live_job_store: SqliteLiveJobStore | None = None,
               secret_vault: FileSecretVault | None = None,
               history_store: HistoryStore | None = None,
               repository_cards: RepositoryCards | None = None,
               enable_legacy_sync_live: bool = False) -> FastAPI:
    app = FastAPI(
        title="LLM Fingerprinting Backend — M6 Local Prototype",
        description="Authenticated encrypted live jobs and mock jobs; judge remains mocked.",
        version="0.6.0",
    )
    app.state.analysis_gateway = gateway if gateway is not None else make_mock_gateway()
    # Mock jobs contain NO API keys. Their worker is a separate process sharing
    # this SQLite path; no task is started in the request handler.
    app.state.job_store = job_store if job_store is not None else SqliteJobStore(
        os.environ.get("SYSTEM_JOB_DB_PATH")
    )
    # The live route shares the versioned six Harness probes and mock judge,
    # but it never stores a user's key or SDK client on the application.
    mock_workflow = getattr(app.state.analysis_gateway, 'workflow', None)
    if mock_workflow is None and live_gateway is None:
        mock_workflow = make_mock_gateway().workflow
    app.state.live_analysis_gateway = (live_gateway if live_gateway is not None
                                       else LiveOpenAIAnalysisGateway(mock_workflow))
    # The authenticated live service is disabled unless BOTH token provision
    # and the shared worker encryption key are configured. No unsafe fallback.
    app.state.token_auth = token_auth or default_auth()
    crypto = LiveCrypto.from_env() if live_job_store is None else live_job_store.crypto
    app.state.live_job_store = live_job_store or (
        SqliteLiveJobStore(crypto, os.environ.get('SYSTEM_JOB_DB_PATH')) if crypto else None)
    app.state.secret_vault = secret_vault or (
        FileSecretVault(crypto) if crypto else None)
    app.state.live_jobs_configured = (app.state.token_auth is not None
                                     and app.state.live_job_store is not None
                                     and app.state.secret_vault is not None)
    # M5: public research cards are read from sibling repository cards/;
    # owner-scoped manually reviewed baseline snapshots live in local SQLite.
    app.state.catalog = ModelCatalog.from_file(Path(__file__).resolve().parents[1] / 'catalog' / 'models.json')
    app.state.repository_cards = repository_cards or RepositoryCards()
    app.state.history_store = history_store or HistoryStore(os.environ.get('SYSTEM_JOB_DB_PATH'))
    app.include_router(history_router)
    app.state.enable_legacy_sync_live = enable_legacy_sync_live or (
        os.environ.get('SYSTEM_ENABLE_LEGACY_SYNC_LIVE') == '1')

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request: Request, exc: RequestValidationError):
        # Pydantic/FastAPI normally echo invalid `input` in 422 JSON, which
        # could expose an accidentally submitted API key. Strip it and `ctx`.
        safe_errors = [
            {"type": err.get("type", "invalid"),
             "loc": err.get("loc", ()),
             "msg": err.get("msg", "Invalid input")}
            for err in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/v1/capabilities", response_model=CapabilitiesResponse)
    def capabilities(request: Request) -> CapabilitiesResponse:
        return CapabilitiesResponse(
            live_jobs_available=request.app.state.live_jobs_configured,
            accepts_api_keys=(request.app.state.live_jobs_configured or
                              request.app.state.enable_legacy_sync_live),
            live_provider_available=(request.app.state.live_jobs_configured or
                                     request.app.state.enable_legacy_sync_live),
            manual_baseline_history_available=request.app.state.token_auth is not None,
            repository_card_lookup_available=(
                getattr(request.app.state.repository_cards, 'card_source', None) is not None and
                request.app.state.repository_cards.card_source.is_file()),
        )

    @app.post("/api/v1/analyze", response_model=AnalyzeResponse)
    def analyze(
        payload: AnalyzeRequest,
        service: MockAnalysisGateway = Depends(get_analysis_gateway),
    ) -> AnalyzeResponse:
        try:
            report = service.analyze(payload.prompt_text, use_stage1=payload.use_stage1)
        except BaselineRequiredError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except Exception:
            # Never leak a provider exception, input text, or future API secret
            # into the HTTP error payload. Production logging must be redacted.
            raise HTTPException(status_code=500, detail="Analysis failed") from None
        fingerprint = report.fingerprint
        return AnalyzeResponse(
            request_id=report.request_id,
            status=fingerprint.final.status,
            model_id=fingerprint.final.model_id,
            stage1_enabled=fingerprint.stage1_enabled,
            model_card_status=report.model_card_status,
            change_status=report.change_status,
            target_queries=report.target_queries,
            report=report.to_dict(),
        )

    @app.post("/api/v1/analyze/live", response_model=LiveOpenAIAnalyzeResponse)
    def analyze_live(
        request: Request,
        payload: LiveOpenAIAnalyzeRequest,
        service: LiveOpenAIAnalysisGateway = Depends(get_live_analysis_gateway),
    ) -> LiveOpenAIAnalyzeResponse:
        """Synchronous OpenAI target interrogation; judge remains a mock.

        This endpoint must be called only against localhost until authentication,
        HTTPS, rate limiting, and job execution are implemented. API keys are
        supplied per request and are NOT stored by the application.
        """
        if not request.app.state.enable_legacy_sync_live:
            # Existing synchronous secret-bearing endpoint is opt-in local dev
            # only. Authenticated async jobs should be used instead.
            raise HTTPException(status_code=404, detail="Legacy live route disabled")
        try:
            report = service.analyze(
                payload.prompt_text,
                api_key=payload.api_key.get_secret_value(),
                target_model=payload.target_model,
                use_stage1=payload.use_stage1,
            )
        except BaselineRequiredError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except ProviderRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail={
                "code": exc.code, "message": exc.message,
            }) from None
        except Exception:
            # Never return SDK exception text, prompt or credential.
            raise HTTPException(status_code=500, detail="Analysis failed") from None
        fingerprint = report.fingerprint
        return LiveOpenAIAnalyzeResponse(
            request_id=report.request_id,
            status=fingerprint.final.status,
            model_id=fingerprint.final.model_id,
            stage1_enabled=fingerprint.stage1_enabled,
            model_card_status=report.model_card_status,
            change_status=report.change_status,
            target_queries=report.target_queries,
            report=report.to_dict(),
        )

    @app.post("/api/v1/fingerprint/jobs", response_model=CreateJobResponse, status_code=202)
    def create_mock_job(payload: CreateMockJobRequest, response: Response,
                        request: Request) -> CreateJobResponse:
        """Queue mock-only analysis; worker runs separately. Never accept keys."""
        if payload.use_stage1:
            raise HTTPException(status_code=409,
                                detail="Stage 1 requires a saved, confirmed baseline; unavailable in mock jobs")
        job = request.app.state.job_store.enqueue_mock(payload.prompt_text)
        response.headers["Location"] = f"/api/v1/fingerprint/jobs/{job['job_id']}"
        return CreateJobResponse(**job)

    @app.get("/api/v1/fingerprint/jobs/{job_id}", response_model=JobStatusResponse)
    def get_mock_job(job_id: str, request: Request) -> JobStatusResponse:
        job = request.app.state.job_store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobStatusResponse(**job)

    @app.post('/api/v1/fingerprint/live-jobs', response_model=CreateLiveJobResponse,
              status_code=202)
    def create_live_job(payload: CreateLiveJobRequest, request: Request,
                        response: Response, user: str = Depends(require_user)) -> CreateLiveJobResponse:
        """Never put the user's provider key in the SQLite job payload."""
        if not request.app.state.live_jobs_configured:
            raise HTTPException(status_code=503, detail='Authenticated live jobs are not configured')
        if payload.use_stage1:
            raise HTTPException(status_code=409,
                                detail='Stage 1 needs a previously confirmed deployment baseline')
        deployment_id = payload.deployment_id
        baseline = None
        target_model = payload.target_model
        if deployment_id is not None:
            try:
                deployment = request.app.state.history_store.get_deployment(user, deployment_id)
            except NotFound:
                # Same status for unknown and other-user deployment IDs.
                raise HTTPException(status_code=404, detail='Deployment not found') from None
            if deployment['provider'] != payload.provider:
                raise HTTPException(status_code=409, detail='Provider does not match deployment')
            if target_model is not None and target_model != deployment['requested_model_id']:
                raise HTTPException(status_code=409, detail='Target model does not match deployment')
            target_model = deployment['requested_model_id']
            previous = deployment['baseline']
            if previous is not None:
                baseline = {
                    'id': previous['id'], 'revision': previous['revision'],
                    'model_id': previous['model_id'],
                    'confirmed_at': previous['confirmed_at'],
                    'card_status': previous['card_status'],
                    'card_snapshot_sha256': previous['card_snapshot_sha256'],
                    'confirmation_source': previous['confirmation_source'],
                }
        job_id = str(uuid4())
        vault = request.app.state.secret_vault
        try:
            vault.put(job_id, user, payload.api_key.get_secret_value())
            job = request.app.state.live_job_store.enqueue(
                user, payload.prompt_text, target_model, job_id=job_id,
                deployment_id=deployment_id, baseline=baseline)
        except Exception:
            vault.delete(job_id)
            raise HTTPException(status_code=500, detail='Could not create analysis job') from None
        response.headers['Location'] = f'/api/v1/fingerprint/live-jobs/{job_id}'
        return CreateLiveJobResponse(**job)

    @app.get('/api/v1/fingerprint/live-jobs/{job_id}', response_model=LiveJobStatusResponse)
    def get_live_job(job_id: str, request: Request,
                     user: str = Depends(require_user)) -> LiveJobStatusResponse:
        if not request.app.state.live_jobs_configured:
            raise HTTPException(status_code=503, detail='Authenticated live jobs are not configured')
        job = request.app.state.live_job_store.get_for_owner(job_id, user)
        if job is None:
            # Do not disclose existence of another user's job.
            raise HTTPException(status_code=404, detail='Job not found')
        return LiveJobStatusResponse(**job)

    @app.get('/api/v1/deployments/{deployment_id}/jobs', response_model=DeploymentJobsResponse)
    def list_deployment_jobs(deployment_id: str, request: Request,
                             user: str = Depends(require_user)):
        try:
            request.app.state.history_store.get_deployment(user, deployment_id)
        except NotFound:
            raise HTTPException(status_code=404, detail='Deployment not found') from None
        if not request.app.state.live_jobs_configured:
            raise HTTPException(status_code=503, detail='Authenticated live jobs are not configured')
        return {'deployment_id': deployment_id,
                'jobs': request.app.state.live_job_store.list_for_deployment(user, deployment_id)}

    return app


app = create_app()
