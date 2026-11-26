"""FastAPI Milestone 3: mock jobs, mock endpoint, opt-in live OpenAI endpoint.

From the repository root:
    python -m uvicorn system.backend.app:app --host 127.0.0.1 --port 8000 --reload

This application is NOT public/production: no authentication, credential vault,
user history, secure prompt retention, or validated live identification exists.
The live endpoint accepts a per-request key in the JSON body. HTTPS is required
before hosting this beyond the local development machine.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .dependencies import get_analysis_gateway, get_live_analysis_gateway
from .schemas import (
    AnalyzeRequest, AnalyzeResponse, LiveOpenAIAnalyzeRequest,
    LiveOpenAIAnalyzeResponse, CapabilitiesResponse, HealthResponse,
    CreateMockJobRequest, CreateJobResponse, JobStatusResponse
)
from .services.analysis import BaselineRequiredError, MockAnalysisGateway, make_mock_gateway
from .services.live import LiveOpenAIAnalysisGateway
from .providers.openai import ProviderRequestError
from .jobs.store import SqliteJobStore


def create_app(gateway: MockAnalysisGateway | None = None,
               live_gateway: LiveOpenAIAnalysisGateway | None = None,
               job_store: SqliteJobStore | None = None) -> FastAPI:
    app = FastAPI(
        title="LLM Fingerprinting Backend — M3 Local Prototype",
        description="Persistent mock jobs plus synchronous mock/OpenAI endpoints; judge remains mocked.",
        version="0.3.0",
    )
    app.state.analysis_gateway = gateway if gateway is not None else make_mock_gateway()
    # Mock jobs contain NO API keys. Their worker is a separate process sharing
    # this SQLite path; no task is started in the request handler.
    import os
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
    def capabilities() -> CapabilitiesResponse:
        return CapabilitiesResponse()

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
        payload: LiveOpenAIAnalyzeRequest,
        service: LiveOpenAIAnalysisGateway = Depends(get_live_analysis_gateway),
    ) -> LiveOpenAIAnalyzeResponse:
        """Synchronous OpenAI target interrogation; judge remains a mock.

        This endpoint must be called only against localhost until authentication,
        HTTPS, rate limiting, and job execution are implemented. API keys are
        supplied per request and are NOT stored by the application.
        """
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

    return app


app = create_app()
