"""Config-driven MOCK factory demonstration; never loads actual classifier models.

Run from repository root:
    python examples/factory_demo.py
    python examples/factory_demo.py config/experiments/lora_only.yaml
    python examples/factory_demo.py config/evaluation.yaml
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fingerprinting.config import load_pipeline_config
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import (EvaluationCase, FingerprintRequest, IdentificationResult,
                                    Observation, Stage1Result)
from fingerprinting.testing import StubStage1, StubIdentifier


def main():
    config_path = ROOT / (sys.argv[1] if len(sys.argv) > 1 else 'config/production.yaml')
    catalog = ModelCatalog.from_file(ROOT / 'catalog/models.json')
    registry = ArtifactRegistry(ROOT, catalog)
    config = load_pipeline_config(config_path, registry)
    constructors = AdapterConstructors()

    def build_stage1(manifest, selection):
        return StubStage1(
            f'MOCK_{selection.approach}:{manifest.artifact_id}',
            Stage1Result('mismatch', predicted_family_id='llama',
                         predicted_model_id='llama3.2-3b', family_match=True,
                         model_match=False, approach=selection.approach))

    def build_identifier(manifest, selection):
        model = 'llama3.2-3b'
        # The values below are test fixtures, not measured model predictions.
        outcome = 'unknown' if selection.adapter == 'lora' else 'identified'
        return StubIdentifier(selection.adapter, IdentificationResult(
            method=selection.adapter, outcome=outcome, candidate_model_id=model,
            accepted_model_id=model if outcome == 'identified' else None,
            diagnostics={'mock': True, 'artifact_id': manifest.artifact_id}))

    constructors.register_stage1('logistic_regression', build_stage1)
    for method in ('lora', 'harness', 'random_forest'):
        constructors.register_stage2(method, build_identifier)

    # Intentionally bypass missing model weights ONLY because all builders above
    # use StubStage1/StubIdentifier. NEVER do this in real inference/deployment.
    pipeline = PipelineFactory(registry, constructors, require_ready=False).build(config)

    observation = Observation('What is recursion?', 'A function can call itself.', 'demo-q')
    req = FingerprintRequest('demo-001', observation, 'llama3.1-8b', 'llama')
    case = EvaluationCase('demo-001', req, 'llama3.2-3b', 'llama', 'mock_demo', 'test')

    result = pipeline.run(req)
    e2e = EvaluationRunner.e2e([case], pipeline)
    stage1 = EvaluationRunner.stage1([case], pipeline.stage1)
    stage2 = EvaluationRunner.stage2([case], pipeline.stage2)
    print('=== MOCK MODEL PREDICTIONS: NOT REAL ACCURACY ===')
    print('Config:', config_path.relative_to(ROOT))
    print('Selection digest:', config.config_sha256)
    print('Pipeline result:', json.dumps(result.to_dict(), indent=2))
    print('Stage 1 metrics (MOCK):', json.dumps(stage1.metrics, indent=2))
    print('Stage 2 metrics (MOCK):', json.dumps(stage2.metrics, indent=2))
    print('E2E metrics (MOCK):', json.dumps(e2e.metrics, indent=2))


if __name__ == '__main__':
    main()
