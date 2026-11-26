"""Evaluate all 132 frozen original P13 RF test responses through Stage 2 Strategy.

Reproduces the original fixed-prompt split for integration testing only.
Do not interpret this as novel-prompt or unseen-model generalization.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fingerprinting.adapters.random_forest import build_random_forest
from fingerprinting.config import load_pipeline_config
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import EvaluationCase, FingerprintRequest, Observation

p=ROOT.parent/'tests/fixtures/random_forest/heldout_raw_cases.jsonl'
def main():
    catalog=ModelCatalog.from_file(ROOT/'catalog/models.json')
    registry=ArtifactRegistry(ROOT,catalog)
    config=load_pipeline_config(ROOT/'config/experiments/random_forest_only.yaml',registry)
    constructors=AdapterConstructors();constructors.register_stage2('random_forest',build_random_forest)
    stage2=PipelineFactory(registry,constructors).build_stage2(config)
    cases=[]
    for r in map(json.loads,p.read_text(encoding='utf-8').splitlines()):
        o=Observation(r['prompt'],r['response_text'],r['prompt_id'],
                      int(float(r['output_tokens'])) if r['output_tokens'] else None,
                      float(r['latency_ms']) if r['latency_ms'] else None)
        request=FingerprintRequest(r['record_id'],o,'llama3.1-8b','llama')
        cases.append(EvaluationCase(r['record_id'],request,r['model_key'],
                                    catalog.get(r['model_key']).family_id, 'fingerprint_v0',
                                    'original_response_held_out',persona_id=r['persona_id']))
    report=EvaluationRunner.stage2(cases,stage2)
    out=ROOT/'reports/random_forest_independent.json'
    out.write_text(json.dumps({'warning': 'Fixed prompt evaluation; rejection policy review_only. Model refitted using sklearn 1.8.0.',
                 'artifact_id':'random_forest/v1', 'config_sha256':config.config_sha256,
                 'metrics':report.metrics},indent=2)+'\n')
    print(out.read_text())

if __name__=='__main__':main()
