"""Run a REAL, checksummed Stage 1 classifier without Stage 2 model files.

Example:
    python examples/stage1_real_demo.py --expected-model llama3.1-8b \
      --response-text 'I am a helpful assistant.' --approach hierarchy_soft
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fingerprinting.adapters.logistic_regression import build_logistic_regression, MODEL_TO_FAMILY
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import FingerprintRequest, Observation


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-model', required=True, choices=sorted(MODEL_TO_FAMILY))
    p.add_argument('--approach', default='hierarchy_hard_route',
                   choices=('hierarchy_hard_route', 'hierarchy_soft', 'ovr_direct'))
    inp = p.add_mutually_exclusive_group(required=True)
    inp.add_argument('--response-text')
    inp.add_argument('--response-file', type=Path)
    args = p.parse_args()
    text = args.response_text if args.response_text is not None else args.response_file.read_text(encoding='utf-8')
    catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')
    registry = ArtifactRegistry(ROOT, catalog)
    config = load_pipeline_config(ROOT/f'config/stage1/{args.approach}.yaml', registry)
    builders = AdapterConstructors()
    builders.register_stage1('logistic_regression', build_logistic_regression)
    verifier = PipelineFactory(registry, builders).build_stage1(config)
    request = FingerprintRequest('stage1-cli', Observation('Original prompt not used by this classifier', text),
                                 args.expected_model, MODEL_TO_FAMILY[args.expected_model])
    result = verifier.verify(request)
    from dataclasses import asdict
    print(json.dumps({'artifact_id': 'stage1_lr/v1', 'config_sha256': config.config_sha256,
                      'manifest_sha256': registry.get('stage1_lr/v1').manifest_sha256,
                      'result': asdict(result)}, indent=2))


if __name__ == '__main__':
    main()
