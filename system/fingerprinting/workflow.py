"""Backend-neutral, prompt-first fingerprinting orchestration.

The user supplies only a prompt; the *backend* supplies an already-authorized
TargetClient, which owns provider configuration and user credentials. This
module never accepts, stores, serializes or logs API keys, and makes no HTTP
calls on its own. The same TargetClient is used for the initial question and
any subsequent versioned Harness probes.

Cards and change history require external authoritative data. Neither a
closed-set candidate nor an absent card is presented as a confirmed result.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .interfaces import CardResolver, TargetClient
from .model_catalog import ModelCatalog
from .pipeline import FingerprintPipeline
from .schemas import FingerprintRequest, Observation, PipelineResult, ProbeQuestion


INITIAL_PROBE_ID = 'UI-INITIAL'


@dataclass(frozen=True)
class BaselineSnapshot:
    """Previous *confirmed* model identity, loaded by an authorized backend.

    A candidate from a review-only classifier MUST NOT become a baseline.
    previous_card is a previously stored card snapshot, not a fresh lookup.
    """
    model_id: str
    previous_card: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError('Baseline requires a confirmed nonempty model ID')
        if self.previous_card is not None and not isinstance(self.previous_card, dict):
            raise ValueError('previous_card must be a dictionary or None')


@dataclass(frozen=True)
class PromptAnalysisReport:
    """Output intended for the API's job result; no raw credentials stored."""
    request_id: str
    fingerprint: PipelineResult
    target_queries: list[str]
    model_card_status: str
    model_card: dict[str, Any] | None
    change_status: str
    previous_model_id: str | None
    current_model_id: str | None
    card_comparison_status: str
    card_changes: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = '1.0'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _TrackedTargetClient:
    def __init__(self, wrapped: TargetClient):
        self.wrapped = wrapped
        self.asked: list[str] = []

    def ask(self, probe: ProbeQuestion) -> Observation:
        result = self.wrapped.ask(probe)
        if not isinstance(result, Observation):
            raise TypeError('TargetClient.ask must return an Observation')
        if result.prompt_text != probe.prompt_text:
            raise ValueError('TargetClient returned an observation for a different prompt')
        self.asked.append(probe.probe_id)
        return result


def _card_changes(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare public card fields; snapshots must refer to the same domain/schema."""
    changes = []
    for field in sorted(old.keys() | new.keys()):
        if old.get(field) != new.get(field):
            changes.append({'field': field, 'before': old.get(field), 'after': new.get(field)})
    return changes


class PromptAnalysisService:
    """One-prompt entry point for backend/UI integration (NOT an HTTP server).

    The browser does not supply the model response or any fingerprint probes.
    A backend API client uses the user's already-authorized provider connection
    to obtain the initial reply and all subsequent required probes.
    """

    def __init__(self, pipeline: FingerprintPipeline, catalog: ModelCatalog, *,
                 card_resolver: CardResolver | None = None):
        self.pipeline = pipeline
        self.catalog = catalog
        self.card_resolver = card_resolver

    def analyze(self, prompt_text: str, target_client: TargetClient, *,
                request_id: str, deployment_id: str | None = None,
                baseline: BaselineSnapshot | None = None,
                domain: str | None = None, use_stage1: bool = False) -> PromptAnalysisReport:
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            raise ValueError('A nonempty user prompt is required')
        if type(use_stage1) is not bool:
            raise ValueError('use_stage1 must be Boolean')
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError('request_id must be nonempty')
        if use_stage1 and baseline is None:
            raise ValueError('Stage 1 requires an authorized prior/expected model baseline')
        expected = baseline.model_id if baseline is not None else None
        family = self.catalog.get(expected).family_id if use_stage1 else None
        # Validate BEFORE the provider API call so invalid inputs do not cost money.
        client = _TrackedTargetClient(target_client)
        initial = client.ask(ProbeQuestion(INITIAL_PROBE_ID, prompt_text))
        request = FingerprintRequest(
            request_id=request_id, initial=initial,
            expected_model_id=expected, expected_family_id=family,
            deployment_id=deployment_id, domain=domain)
        result = self.pipeline.run(request, target_client=client, use_stage1=use_stage1)
        model_id = (result.final.model_id if result.final.status in
                    ('identified', 'verified', 'drift_detected') else None)
        card = result.domain_card
        if card is None and model_id is not None and self.card_resolver is not None:
            try:
                card = self.card_resolver.resolve(model_id, domain)
            except Exception:
                card = None
        if not isinstance(card, dict):
            card = None
        card_status = 'unconfirmed' if model_id is None else ('available' if card is not None else 'unavailable')
        if baseline is None:
            change_status = 'no_baseline'
        elif model_id is None:
            change_status = 'unresolved'
        elif model_id == baseline.model_id:
            change_status = 'same_model'
        else:
            change_status = 'model_changed'
        card_comp = 'not_comparable'
        differences: list[dict[str, Any]] = []
        if baseline is not None and model_id is not None and card is not None and baseline.previous_card is not None:
            compatible = all(
                baseline.previous_card.get(k) is None or card.get(k) is None or
                baseline.previous_card[k] == card[k]
                for k in ('schema_version', 'domain')
            )
            if compatible:
                card_comp = 'compared'
                differences = _card_changes(baseline.previous_card, card)
        return PromptAnalysisReport(
            request_id=request_id, fingerprint=result,
            target_queries=list(client.asked),
            model_card_status=card_status, model_card=card,
            change_status=change_status, previous_model_id=expected,
            current_model_id=model_id,
            card_comparison_status=card_comp, card_changes=differences)
