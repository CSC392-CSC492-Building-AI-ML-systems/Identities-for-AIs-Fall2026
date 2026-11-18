"""Shared data contracts for the two-stage LLM fingerprinting pipeline.

This module intentionally imports no model-specific code or third-party packages.
It defines shapes, not fingerprinting behaviour or evaluation metrics.
Compatible with Python 3.10+.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Stage1Verdict = Literal["verified", "mismatch", "inconclusive", "error", "skipped"]
MethodName = Literal["lora", "harness", "random_forest"]
MethodOutcome = Literal["identified", "unknown", "unsupported", "error"]
FinalStatus = Literal["verified", "drift_detected", "identified", "needs_review", "error"]


@dataclass(frozen=True)
class Observation:
    """One prompt-response pair; optional measurements may be missing in replay/live mode."""

    prompt_text: str
    response_text: str
    prompt_id: str | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None

    def __post_init__(self) -> None:
        if not self.prompt_text.strip():
            raise ValueError("Observation.prompt_text must not be empty")
        if not self.response_text.strip():
            raise ValueError("Observation.response_text must not be empty")
        if self.output_tokens is not None and self.output_tokens < 0:
            raise ValueError("output_tokens must not be negative")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")


@dataclass(frozen=True)
class ProbeQuestion:
    probe_id: str
    prompt_text: str

    def __post_init__(self) -> None:
        if not self.probe_id.strip() or not self.prompt_text.strip():
            raise ValueError("ProbeQuestion must contain a nonempty ID and text")


@dataclass(frozen=True)
class FingerprintRequest:
    """Runtime input. Never add actual/ground-truth identity here."""

    request_id: str
    initial: Observation
    expected_model_id: str | None = None
    expected_family_id: str | None = None
    deployment_id: str | None = None
    domain: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id must not be empty")
        if self.expected_model_id is not None and (not isinstance(self.expected_model_id, str) or not self.expected_model_id.strip()):
            raise ValueError("Expected model must be a nonempty string or None")
        if self.expected_family_id is not None and (not isinstance(self.expected_family_id, str) or not self.expected_family_id.strip()):
            raise ValueError("Expected family must be a nonempty string or None")
        if self.expected_family_id is not None and self.expected_model_id is None:
            raise ValueError("Expected family requires an expected model ID")


@dataclass(frozen=True)
class Stage1Result:
    """A mismatch means 'not verified', NOT ground-truth evidence of model drift."""

    verdict: Stage1Verdict
    predicted_family_id: str | None = None
    predicted_model_id: str | None = None
    family_match: bool | None = None
    model_match: bool | None = None  # None means not attempted / unavailable.
    approach: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    duration_ms: float | None = None


@dataclass(frozen=True)
class IdentificationInput:
    """What Stage 2 sees. Expected/true identity intentionally excluded."""

    initial: Observation
    probes: dict[str, Observation] = field(default_factory=dict)
    deployment_id: str | None = None
    domain: str | None = None


@dataclass(frozen=True)
class IdentificationResult:
    """Single Stage 2 method's output; score_type prevents score conflation."""

    method: MethodName
    outcome: MethodOutcome
    candidate_model_id: str | None = None  # May be a guess even if unaccepted.
    accepted_model_id: str | None = None   # Present only on an accepted identification.
    score: float | None = None
    score_type: str | None = None  # e.g. fit_score, max_softmax, rf_vote_fraction
    handoff_requested: bool | None = None  # Method recommendation, not orchestrator decision.
    model_scores: dict[str, float] = field(default_factory=dict)
    probe_ids_used: list[str] = field(default_factory=list)
    reason: str = ""
    duration_ms: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.outcome == "identified" and not self.accepted_model_id:
            raise ValueError("Identified outcomes require accepted_model_id")
        if self.outcome != "identified" and self.accepted_model_id is not None:
            raise ValueError("Unaccepted outcomes must not contain accepted_model_id")
        if self.score is not None and not self.score_type:
            raise ValueError("A score must have a score_type")


@dataclass(frozen=True)
class FinalResult:
    status: FinalStatus
    model_id: str | None  # None means unresolved; NOT the known expected model.
    resolved_by: Literal["stage1", "lora", "harness", "random_forest"] | None
    reason: str

    def __post_init__(self) -> None:
        if self.status in ("verified", "drift_detected", "identified") and not self.model_id:
            raise ValueError("Resolved statuses must include model_id")
        if self.status in ("needs_review", "error") and self.model_id is not None:
            raise ValueError("Unresolved statuses must not claim a model_id")
        if self.status in ("verified", "drift_detected", "identified") and self.resolved_by is None:
            raise ValueError("Resolved statuses must identify the deciding method")
        if self.status in ("needs_review", "error") and self.resolved_by is not None:
            raise ValueError("Unresolved statuses must not claim a deciding method")


@dataclass(frozen=True)
class Stage2Run:
    """Outputs of an interchangeable Stage 2 execution strategy.

    selected_attempt_index is the *accepted* attempt; None means unresolved.
    A method can suggest handoff even if it proposes a candidate identity.
    """

    strategy: str
    attempts: list[IdentificationResult]
    selected_attempt_index: int | None = None
    probe_ids_collected: list[str] = field(default_factory=list)
    duration_ms: float | None = None

    def __post_init__(self) -> None:
        if self.selected_attempt_index is not None:
            i = self.selected_attempt_index
            if i < 0 or i >= len(self.attempts):
                raise ValueError("selected_attempt_index out of bounds")
            chosen = self.attempts[i]
            if (chosen.outcome != "identified" or chosen.accepted_model_id is None
                    or chosen.handoff_requested is True):
                raise ValueError("Selected attempt must be an accepted, non-handoff identification")

    @property
    def accepted_model_id(self) -> str | None:
        if self.selected_attempt_index is None:
            return None
        return self.attempts[self.selected_attempt_index].accepted_model_id

    @property
    def resolved_by(self) -> MethodName | None:
        if self.selected_attempt_index is None:
            return None
        return self.attempts[self.selected_attempt_index].method


@dataclass(frozen=True)
class PipelineResult:
    """One result per run; all attempted methods retained for diagnostics."""

    request_id: str
    stage1: Stage1Result
    stage2_attempts: list[IdentificationResult]
    final: FinalResult
    schema_version: str = "1.1"
    duration_ms: float | None = None
    domain_card: dict[str, Any] | None = None
    stage1_strategy: str | None = None
    stage1_enabled: bool = False
    stage2_strategy: str | None = None
    routing_trace: list[str] = field(default_factory=list)
    # Filled by PipelineFactory; direct Strategy Pattern construction may omit them.
    config_sha256: str | None = None
    artifact_ids: dict[str, str] = field(default_factory=dict)
    manifest_sha256: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Result is JSON-compatible if the optional diagnostics/card are JSON-compatible."""
        return asdict(self)


@dataclass(frozen=True)
class EvaluationCase:
    """Offline ground truth, held only by the evaluator; never sent to fingerprint()."""

    case_id: str
    request: FingerprintRequest
    actual_model_id: str
    actual_family_id: str
    dataset_id: str
    split_id: str
    # The runner supplies these to a replay client only when a method requests a probe.
    replay_probes: dict[str, Observation] = field(default_factory=dict)
    persona_id: str | None = None
    prompt_group_id: str | None = None
    source_record_ids: list[str] = field(default_factory=list)
