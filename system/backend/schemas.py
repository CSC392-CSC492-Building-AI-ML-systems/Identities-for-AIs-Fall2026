"""Public HTTP contracts for the offline-only backend Milestone 1."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


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


class LiveOpenAIAnalyzeResponse(BaseModel):
    """Real OpenAI target answers, MOCK judge, no accepted identification."""

    schema_version: Literal["1.0"] = "1.0"
    mode: Literal["live_target_mock_judge"] = "live_target_mock_judge"
    request_id: str
    status: Literal["identified", "verified", "drift_detected", "needs_review", "error"]
    model_id: str | None
    stage1_enabled: bool
    model_card_status: str
    change_status: str
    target_queries: list[str]
    report: dict[str, Any]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["mock"] = "mock"


class CapabilitiesResponse(BaseModel):
    mode: Literal["mock"] = "mock"
    prompt_only: bool = True
    stage1_enabled_by_default: bool = False
    stage1_available: bool = False
    accepts_api_keys: bool = True  # Only /api/v1/analyze/live; never the mock endpoint
    live_provider_available: bool = True  # Route exists; credentials not verified
    live_target_providers: list[str] = ["openai"]
    live_judge_available: bool = False
    accepted_model_identification_available: bool = False
    synchronous_prototype_only: bool = False  # New mock job route is asynchronous via a separate worker.
    durable_mock_jobs_available: bool = True
    live_jobs_available: bool = False
    job_worker_required: bool = True
    verified_model_cards: bool = False
    confirmed_baselines: bool = False


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
