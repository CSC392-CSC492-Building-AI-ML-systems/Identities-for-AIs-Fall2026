"""Real Stage 1 + original Harness logic with MOCK judge (no API calls).

Shows end-to-end routing only, not a real identification-accuracy evaluation.
The LoRA and RF methods are deliberately excluded from this test configuration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fingerprinting.adapters.harness import HarnessIdentifier
from fingerprinting.adapters.logistic_regression import build_logistic_regression
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import FingerprintRequest, Observation
from fingerprinting.strategies import ReplayTargetClient


def main():
    registry = ArtifactRegistry(ROOT, ModelCatalog.from_file(ROOT/'catalog/models.json'))
    config = load_pipeline_config(ROOT/'config/experiments/stage1_harness.yaml', registry)
    constructors = AdapterConstructors()
    constructors.register_stage1('logistic_regression', build_logistic_regression)
    constructors.register_stage2('harness', lambda m, s: HarnessIdentifier(m, judge_provider='mock'))
    pipeline = PipelineFactory(registry, constructors).build(config)
    sample = json.loads((ROOT.parent/'tests/fixtures/harness_replay/llama3.1-8b_BK1_sample2.json').read_text())
    prompts = pipeline.stage2.identifiers[0].required_probes()
    replays = {p.probe_id: Observation(p.prompt_text, sample[p.probe_id], p.probe_id) for p in prompts}
    request = FingerprintRequest(
        request_id='harness-e2e-mock-demo',
        initial=Observation('What is your model?', sample['I2'], 'I2'),
        expected_model_id='gemini-3.1-pro', expected_family_id='gemini', domain='risk')
    result = pipeline.run(request, target_client=ReplayTargetClient(replays))
    print(json.dumps({'note': 'Mock judge never establishes exact identity; no accuracy claim',
                      'final': result.to_dict()['final'], 'routing_trace': result.routing_trace,
                      'stage2_attempts': [x.method for x in result.stage2_attempts],
                      'probe_count': 6 if result.stage2_attempts else 0,
                      'artifact_ids': result.artifact_ids}, indent=2))


if __name__ == '__main__':
    main()
