"""Complete real Stage 1 -> Stage 2C RF (without LoRA or Harness).
The pipeline calls RF only when Stage 1 cannot verify the expected model.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fingerprinting.adapters.logistic_regression import build_logistic_regression
from fingerprinting.adapters.random_forest import build_random_forest
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import FingerprintRequest, Observation

def main():
    registry=ArtifactRegistry(ROOT,ModelCatalog.from_file(ROOT/'catalog/models.json'))
    cfg=load_pipeline_config(ROOT/'config/experiments/random_forest_only.yaml',registry)
    constructors=AdapterConstructors()
    constructors.register_stage1('logistic_regression',build_logistic_regression)
    constructors.register_stage2('random_forest',build_random_forest)
    pipeline=PipelineFactory(registry,constructors).build(cfg)
    rows=[json.loads(x) for x in (ROOT/'testdata/random_forest/heldout_raw_cases.jsonl').read_text().splitlines()]
    row=next(r for r in rows if r['model_key']=='gemma3-4b')
    obs=Observation(row['prompt'],row['response_text'],row['prompt_id'],
                    int(float(row['output_tokens'])),float(row['latency_ms']))
    result=pipeline.run(FingerprintRequest('stage1-rf-demo',obs,'llama3.1-8b','llama'))
    print(json.dumps(result.to_dict(),indent=2))

if __name__=='__main__':main()
