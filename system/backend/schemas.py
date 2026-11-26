"""Public HTTP contracts for the offline-only backend Milestone 1."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class AnalyzeRequest(BaseModel):
    """The UI supplies one prompt; never a response, probe list, or API key.

    Unknown fields are rejected so that a user cannot accidentally post an
    API key to this mock-only endpoint.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    prompt_text: str = Field(min_length=1, max_length=8000)
    use_stage1: bool = False

    @field_validator("prompt_text")
    @classmethod
    def nonblank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt must not be blank")
        return value


class AnalyzeResponse(BaseModel):
    """A completed synchronous MOCK report, not a live fingerprint result."""

    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["mock"] = "mock"
    request_id: str
    status: Literal["identified", "verified", "drift_detected", "needs_review", "error"]
    model_id: str | None
    stage1_enabled: bool
    model_card_status: str
    change_status: str
    target_queries: list[str]
    report: dict[str, Any]


class LiveOpenAIAnalyzeRequest(BaseModel):
    """Per-analysis OpenAI key; never persisted or serialized in the result.

    The model ID routes requests to a specific OpenAI deployment. It is NOT
    supplied as a fingerprinting ground truth or predicted identity.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    prompt_text: str = Field(min_length=1, max_length=8000)
    provider: Literal["openai"] = "openai"
    target_model: str = Field(min_length=1, max_length=100,
                              pattern=r"^[A-Za-z0-9._:-]+$")
    api_key: SecretStr
    use_stage1: bool = False

    @field_validator("prompt_text")
    @classmethod
    def nonblank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt must not be blank")
        return value

    @field_validator("api_key")
    @classmethod
    def nonblank_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("API key must not be blank")
        return value


class BaselineReference(BaseModel):
    id: str
    revision: int
    model_id: str
    confirmed_at: str | None = None
    confirmation_source: str | None = None
    card_status: str | None = None
    card_snapshot_sha256: str | None = None


class IdentificationView(BaseModel):
    status: Literal['needs_review']
    accepted_model_id: None = None
    reason: Literal['live_judge_not_validated', 'acceptance_not_validated', 'methods_failed']


class CardComparisonView(BaseModel):
    status: Literal['not_comparable']
    changes: list[dict[str, Any]] = Field(default_factory=list)


class ComparisonView(BaseModel):
    status: Literal['no_baseline', 'insufficient_evidence']
    previous_model_id: str | None
    current_model_id: None = None
    identity_change: None = None
    family_change: None = None
    card_comparison: CardComparisonView


class ModelCardView(BaseModel):
    status: Literal['unavailable']
    model_id: None = None
    card: None = None


class ResultEvidenceView(BaseModel):
    target_provider: Literal['openai']
    judge: Literal['mock', 'google', 'openai', 'not_configured']
    identity_confirmed: Literal[False]
    baseline_auto_updated: Literal[False]


class MethodCandidateView(BaseModel):
    method: Literal['lora', 'harness', 'random_forest']
    artifact_id: str | None = None
    status: Literal['candidate', 'abstained', 'error', 'not_configured', 'mock_judge']
    candidate_model_id: str | None = None
    score: float | None = None
    score_type: str | None = None
    probe_ids_used: list[str] = Field(default_factory=list)


class UnifiedLiveResult(BaseModel):
    """Safe, typed UI result. Raw report remains for research diagnostics."""
    schema_version: Literal['1.0'] = '1.0'
    identification: IdentificationView
    comparison: ComparisonView
    model_card: ModelCardView
    baseline: BaselineReference | None
    evidence: ResultEvidenceView
    method_candidates: list[MethodCandidateView] = Field(default_factory=list)
    candidate_agreement: Literal["none", "single_candidate", "agree", "disagree"] = "none"


class LiveOpenAIAnalyzeResponse(BaseModel):
    """Real target responses; legacy mock or review-only Stage 2 evidence."""

    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["live_target_mock_judge", "live_stage2_review"] = "live_target_mock_judge"
    request_id: str
    status: Literal["identified", "verified", "drift_detected", "needs_review", "error"]
    model_id: str | None
    stage1_enabled: bool
    model_card_status: str
    change_status: str
    target_queries: list[str]
    report: dict[str, Any]
    ui_result: UnifiedLiveResult | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["mock"] = "mock"


class CapabilitiesResponse(BaseModel):
    mode: Literal["mock"] = "mock"
    prompt_only: bool = True
    stage1_enabled_by_default: bool = False
    stage1_available: bool = False
    accepts_api_keys: bool = False  # True only after authenticated live jobs configured
    live_provider_available: bool = False  # Available to API only when configured
    live_target_providers: list[str] = ["openai"]
    live_judge_available: bool = False
    stage2_review_jobs_supported: bool = True  # API contract only, not worker liveness
    accepted_model_identification_available: bool = False
    synchronous_prototype_only: bool = False  # New mock job route is asynchronous via a separate worker.
    durable_mock_jobs_available: bool = True
    live_jobs_available: bool = False
    live_jobs_require_bearer_token: bool = True
    job_worker_required: bool = True
    verified_model_cards: bool = False
    confirmed_baselines: bool = False
    manual_baseline_history_available: bool = True
    repository_card_lookup_available: bool = False


class CreateMockJobRequest(AnalyzeRequest):
    """Only a prompt and Stage 1 flag; unknown fields (especially keys) rejected.

    Stage 1 is not enabled in the mock worker because no confirmed baseline
    store has been implemented; the route rejects that combination with 409.
    """


class CreateJobResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: str
    mode: Literal["mock"] = "mock"
    status: Literal["queued"] = "queued"
    created_at: str


class JobStatusResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: str
    mode: Literal["mock"] = "mock"
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    attempt_count: int
    result: AnalyzeResponse | None
    error_code: str | None


class CreateLiveJobRequest(LiveOpenAIAnalyzeRequest):
    """Authenticated live job. Link to a reviewed deployment when available.

    If linked, the backend derives the routing model from that owned deployment;
    no user-provided routing value is ever treated as an inferred identity.
    """
    mode: Literal["live_target_mock_judge", "live_stage2_review"] = "live_target_mock_judge"
    allow_live_judge: bool = False
    target_model: str | None = Field(default=None, min_length=1, max_length=100,
                                      pattern=r"^[A-Za-z0-9._:-]+$")
    deployment_id: str | None = Field(default=None, min_length=1, max_length=100,
                                       pattern=r"^[A-Za-z0-9-]+$")

    @model_validator(mode='after')
    def target_or_deployment(self):
        if self.allow_live_judge and self.mode != "live_stage2_review":
            raise ValueError("External judge consent requires Stage 2 review mode")
        if self.target_model is None and self.deployment_id is None:
            raise ValueError('Provide target_model or deployment_id')
        return self


class CreateLiveJobResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: str
    mode: Literal["live_target_mock_judge", "live_stage2_review"] = "live_target_mock_judge"
    status: Literal["queued"] = "queued"
    created_at: str
    deployment_id: str | None = None
    baseline_revision: int | None = None


class LiveJobStatusResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: str
    mode: Literal["live_target_mock_judge", "live_stage2_review"] = "live_target_mock_judge"
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    attempt_count: int
    result: LiveOpenAIAnalyzeResponse | None
    error_code: str | None
    deployment_id: str | None = None
    baseline_revision: int | None = None


class DeploymentJobListItem(BaseModel):
    job_id: str
    status: Literal['queued', 'running', 'completed', 'failed']
    created_at: str
    updated_at: str
    baseline_revision: int | None
    error_code: str | None


class DeploymentJobsResponse(BaseModel):
    deployment_id: str
    jobs: list[DeploymentJobListItem]
