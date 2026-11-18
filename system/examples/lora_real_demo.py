"""Run the configured, trained LoRA (after installing the real adapter).

This script will *fail clearly* until the weights and pinned base-model commit
have been provided. No mock is used by this entry point.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fingerprinting.adapters.lora import build_lora
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import IdentificationInput, Observation


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--response-text', required=True)
    args = p.parse_args()
    registry = ArtifactRegistry(ROOT, ModelCatalog.from_file(ROOT / 'catalog/models.json'))
    cfg = load_pipeline_config(ROOT / 'config/experiments/lora_only.yaml', registry)
    builders = AdapterConstructors()
    builders.register_stage2('lora', build_lora)
    stage2 = PipelineFactory(registry, builders).build_stage2(cfg)
    outcome = stage2.execute(IdentificationInput(
        initial=Observation('Response provided by caller; prompt unused by LoRA', args.response_text)))
    print(json.dumps({'run': asdict(outcome), 'artifact_id': cfg.stage2.methods[0].artifact_id,
                      'config_sha256': cfg.config_sha256}, indent=2))


if __name__ == '__main__':
    main()
