"""Run the actual trained Stage 2C forest standalone (no API or Stage 1 needed)."""
from __future__ import annotations
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fingerprinting.adapters.random_forest import build_random_forest
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import IdentificationInput, Observation

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt', default='What is the Fibonacci sequence?')
    parser.add_argument('--response', default='The Fibonacci sequence begins with 0, 1, 1, 2, 3, 5.')
    parser.add_argument('--prompt-id', default=None)
    parser.add_argument('--output-tokens', type=int, default=None)
    parser.add_argument('--latency-ms', type=float, default=None)
    args=parser.parse_args()
    registry=ArtifactRegistry(ROOT, ModelCatalog.from_file(ROOT/'catalog/models.json'))
    config=load_pipeline_config(ROOT/'config/experiments/random_forest_only.yaml',registry)
    builders=AdapterConstructors()
    builders.register_stage2('random_forest', build_random_forest)
    strategy=PipelineFactory(registry,builders).build_stage2(config)
    context=IdentificationInput(initial=Observation(args.prompt,args.response,args.prompt_id,
                                                    args.output_tokens,args.latency_ms))
    run=strategy.execute(context)
    print(json.dumps({'artifact_id':config.stage2.methods[0].artifact_id,
                      'config_sha256':config.config_sha256,
                      'run':asdict(run)},indent=2))

if __name__=='__main__':
    main()
