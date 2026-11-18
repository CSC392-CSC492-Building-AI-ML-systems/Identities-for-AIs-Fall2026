"""Execute the installed real Random Forest with Stage 1 OFF by default.

From GitHub root: python system/run.py example stage2_default_real_demo
No external requests, and no LoRA checkpoint required. The forest runs in
review_only mode, so it reports a candidate but does not assert identity.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fingerprinting.adapters.builders import real_adapter_constructors
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import FingerprintRequest, Observation


def main() -> None:
    catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')
    registry = ArtifactRegistry(ROOT, catalog)
    config = load_pipeline_config(ROOT/'config/experiments/random_forest_only.yaml', registry)
    factory = PipelineFactory(registry, real_adapter_constructors(), require_ready=True)
    pipeline = factory.build(config)
    request = FingerprintRequest(
        request_id='stage2-demo',
        initial=Observation(
            prompt_text='What is recursion in programming?',
            response_text='Recursion is when a function calls itself to solve a smaller problem.',
            prompt_id=None,
        ),
    )
    result = pipeline.run(request)
    print(json.dumps(result.to_dict(), indent=2))
    print('\nNote: review_only Random Forest candidates are NOT confirmed identities.')


if __name__ == '__main__':
    main()
