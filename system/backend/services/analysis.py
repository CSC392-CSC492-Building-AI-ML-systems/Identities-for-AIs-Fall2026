"""Mock HTTP analysis gateway reusing the actual prompt-first workflow.

The legacy Harness adapter supplies the *versioned* six probe prompts. The
injected mock judge only returns Unknown; no model is ever falsely accepted.
No Qwen model, RF artifact, API key, live provider or judge call is required.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from system.fingerprinting.adapters.harness import HarnessIdentifier
from system.fingerprinting.clients import CallableTargetClient
from system.fingerprinting.model_catalog import ModelCatalog
from system.fingerprinting.pipeline import FingerprintPipeline
from system.fingerprinting.registry import ArtifactRegistry
from system.fingerprinting.strategies import SingleMethodStrategy
from system.fingerprinting.workflow import PromptAnalysisReport, PromptAnalysisService

from ..providers.mock import MockTargetProvider


class BaselineRequiredError(ValueError):
    """Stage 1 cannot be used without a confirmed prior identity."""


class MockAnalysisGateway:
    """One HTTP-request-sized synchronous analysis using offline doubles."""

    def __init__(self, workflow: PromptAnalysisService, provider: MockTargetProvider):
        self.workflow = workflow
        self.provider = provider

    def analyze(self, prompt_text: str, *, use_stage1: bool = False) -> PromptAnalysisReport:
        # In future, the backend looks up an authenticated user's confirmed
        # deployment baseline. This M1 backend deliberately stores none.
        if use_stage1:
            raise BaselineRequiredError(
                "Stage 1 requires a saved, confirmed baseline; unavailable in the mock prototype"
            )
        client = CallableTargetClient(self.provider.send_prompt)
        return self.workflow.analyze(
            prompt_text, client, request_id=str(uuid4()), use_stage1=False
        )


def _mock_harness_judge(payload):
    # This function is injected; no external judge or API is contacted.
    return {
        "status": "Unknown model",
        "identified": {"model_key": None},
        "fit_score": 0.0,
        "handoff_to_next_method": True,
        "reasons": ["Offline mock judge; identification not performed"],
    }


def make_mock_gateway(system_root: Path | None = None) -> MockAnalysisGateway:
    root = system_root or Path(__file__).resolve().parents[2]
    catalog = ModelCatalog.from_file(root / "catalog/models.json")
    registry = ArtifactRegistry(root, catalog)
    # Read the genuine six Harness questions from the immutable v1 bundle.
    # We deliberately replace the judge, NOT the prompt definitions.
    harness = HarnessIdentifier(
        registry.get("harness/v1"), judge_provider="mock", runner=_mock_harness_judge
    )
    pipeline = FingerprintPipeline(
        None, SingleMethodStrategy(harness), stage1_enabled=False
    )
    workflow = PromptAnalysisService(pipeline, catalog)
    return MockAnalysisGateway(workflow, MockTargetProvider())
