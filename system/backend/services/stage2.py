"""Local review-only Stage 2 gateway, built from the existing Factory.

No Stage 1, acceptance thresholds, or automatic baseline changes. The default
profile uses a deterministic abstaining mock judge and a real RF artifact.
"""
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from ...fingerprinting.adapters.builders import real_adapter_constructors
from ...fingerprinting.adapters.harness import HarnessIdentifier
from ...fingerprinting.clients import CallableTargetClient
from ...fingerprinting.config import load_pipeline_config
from ...fingerprinting.factory import PipelineFactory
from ...fingerprinting.model_catalog import ModelCatalog
from ...fingerprinting.registry import ArtifactRegistry
from ...fingerprinting.workflow import PromptAnalysisService
from .analysis import _mock_harness_judge, BaselineRequiredError
from .live import LiveOpenAIAnalysisGateway

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / 'config/experiments/live_stage2_review.yaml'
METHODS = ('lora', 'harness', 'random_forest')


class NoRetryTargetClient(CallableTargetClient):
    """Do not reissue a failed billable probe during the same analysis."""
    def __init__(self, send_prompt):
        super().__init__(send_prompt)
        self.failed = set()

    def ask(self, probe):
        if probe.probe_id in self.failed:
            raise RuntimeError('Probe already failed in this analysis')
        try:
            return super().ask(probe)
        except Exception:
            self.failed.add(probe.probe_id)
            raise


class ReviewStage2Gateway(LiveOpenAIAnalysisGateway):
    def __init__(self, workflow, judge, *, provider_factory=None):
        super().__init__(workflow, provider_factory)
        self.judge = judge

    def analyze(self, prompt_text, *, api_key, target_model, use_stage1=False):
        if use_stage1:
            raise BaselineRequiredError('Stage 1 is deferred')
        provider = self._provider_factory(api_key, target_model)
        try:
            return self.workflow.analyze(prompt_text, NoRetryTargetClient(provider.send_prompt),
                                         request_id=str(uuid4()), use_stage1=False)
        finally:
            close = getattr(provider, 'close', None)
            if callable(close):
                close()


def make_stage2_gateway(config_path=DEFAULT_CONFIG, *, system_root=ROOT,
                        live_judge=False, provider_factory=None):
    root = Path(system_root)
    catalog = ModelCatalog.from_file(root / 'catalog/models.json')
    registry = ArtifactRegistry(root, catalog)
    config = load_pipeline_config(config_path, registry)
    if config.stage1.enabled or config.cards_enabled:
        raise ValueError('Review prototype requires Stage 1 and automatic cards disabled')
    # No previously accepted artifact or unvalidated label mapping may enter
    # this profile. Configuration is trusted operator input, not HTTP input.
    for choice in config.stage2.methods:
        opts = registry.get(choice.artifact_id).options
        if choice.adapter == 'harness':
            if opts.get('reference_abi') != 'catalog_reference_v2' or opts.get('acceptance_policy') != 'review_only':
                raise ValueError('Use catalog-based review-only Harness')
        elif opts.get('acceptance_policy', {}).get('mode') != 'review_only':
            raise ValueError('Only review-only classifiers allowed')
        if choice.adapter == 'lora' and (opts.get('label_order_status') != 'confirmed' or
                not re.fullmatch('[0-9a-fA-F]{40}', str(opts.get('base_model_revision', '')))):
            raise ValueError('LoRA requires a confirmed label mapping and pinned base revision')
    constructors = real_adapter_constructors(harness_judge_provider=None if live_judge else 'mock')
    if not live_judge:
        constructors.stage2['harness'] = lambda manifest, choice: HarnessIdentifier(
            manifest, judge_provider='mock', runner=_mock_harness_judge)
    pipeline = PipelineFactory(registry, constructors).build(config)
    # Guard shared cache against differing definitions under identical IDs;
    # cap distinct probes before any billable target requests.
    definitions = {}
    for method in pipeline.stage2.identifiers:
        for probe in method.required_probes():
            if definitions.setdefault(probe.probe_id, probe.prompt_text) != probe.prompt_text:
                raise ValueError('Conflicting probe definitions across methods')
    if len(definitions) > 6 or 'UI-INITIAL' in definitions:
        raise ValueError('Prototype permits at most six distinct additional probes')
    harness = next((m for m in pipeline.stage2.identifiers if m.name == 'harness'), None)
    judge = harness.provider if harness else 'not_configured'
    if live_judge and judge not in ('google', 'openai'):
        raise ValueError('Live judge requires a configured Google or OpenAI Harness judge')
    return ReviewStage2Gateway(PromptAnalysisService(pipeline, catalog), judge,
                               provider_factory=provider_factory)
