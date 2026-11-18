"""Run the real versioned Harness code on six recorded probe responses.

--judge-provider mock exercises real rules and cards without judge API calls;
mock guesses are not accepted identities, so accuracy is NOT measured here.
With a real provider credential, this invokes the actual Harness judge API.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fingerprinting.adapters.harness import HarnessIdentifier
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import IdentificationInput, Observation


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--answers', default='testdata/harness_replay/llama3.1-8b_BK1_sample2.json')
    p.add_argument('--judge-provider', choices=['google', 'anthropic', 'openai', 'mock'], default='mock')
    p.add_argument('--domain', choices=['compliance', 'governance', 'evaluation', 'risk'], default='risk')
    p.add_argument('--deployment', default=None)
    args = p.parse_args()
    catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')
    registry = ArtifactRegistry(ROOT, catalog)
    config = load_pipeline_config(ROOT/'config/experiments/harness_only.yaml', registry)
    builders = AdapterConstructors()
    builders.register_stage2('harness', lambda m, s: HarnessIdentifier(m, judge_provider=args.judge_provider))
    method = PipelineFactory(registry, builders).build_stage2(config)
    answers = json.loads((ROOT/args.answers).read_text(encoding='utf-8'))
    probes = method.identifiers[0].required_probes()
    context = IdentificationInput(
        initial=Observation('Initial prompt example', 'Initial response example'),
        probes={p.probe_id: Observation(p.prompt_text, answers[p.probe_id], p.probe_id) for p in probes},
        domain=args.domain, deployment_id=args.deployment)
    result = method.execute(context)
    print(json.dumps({'artifact_id': config.stage2.methods[0].artifact_id,
                      'config_sha256': config.config_sha256,
                      'result': asdict(result)}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
