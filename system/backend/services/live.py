"""Synchronous, per-request OpenAI target gateway for backend Milestone 2.

The Harness judge is intentionally mocked. This proves live target collection,
not real model identification, and NEVER accepts an identity from mock judge.
"""
from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from system.fingerprinting.clients import CallableTargetClient
from system.fingerprinting.workflow import PromptAnalysisService, PromptAnalysisReport

from ..providers.openai import OpenAIResponsesProvider
from .analysis import BaselineRequiredError

ProviderFactory = Callable[[str, str], object]


class LiveOpenAIAnalysisGateway:
    """Credential is used for one request only. Do not store provider objects."""

    def __init__(self, workflow: PromptAnalysisService,
                 provider_factory: ProviderFactory | None = None):
        self.workflow = workflow
        self._provider_factory = provider_factory or (
            lambda api_key, model: OpenAIResponsesProvider(api_key, model)
        )

    def analyze(self, prompt_text: str, *, api_key: str, target_model: str,
                use_stage1: bool = False) -> PromptAnalysisReport:
        if use_stage1:
            raise BaselineRequiredError(
                'Stage 1 requires a saved, confirmed baseline; unavailable in the M2 prototype'
            )
        # The provider lives only for this request (not app.state). The
        # underlying SDK client is not stored in a registry or database.
        provider = self._provider_factory(api_key, target_model)
        try:
            client = CallableTargetClient(provider.send_prompt)
            return self.workflow.analyze(
                prompt_text, client, request_id=str(uuid4()), use_stage1=False
            )
        finally:
            # The provider/client must not survive the request.
            close = getattr(provider, 'close', None)
            if callable(close):
                close()
