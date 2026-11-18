"""CLI for validating a pipeline YAML and inspecting artifact readiness.

Example: python -m fingerprinting.config_cli config/production.yaml --root .
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import check_config_readiness, load_pipeline_config
from .model_catalog import ModelCatalog
from .registry import ArtifactRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path, help='Pipeline YAML selection')
    parser.add_argument('--root', type=Path, default=Path('.'), help='Project root containing models/ and catalog/')
    parser.add_argument('--require-ready', action='store_true', help='Exit with failure unless active artifacts are ready')
    parser.add_argument('--use-stage1', action='store_true', help='Also check Stage 1 readiness (off by default)')
    args = parser.parse_args()
    catalog = ModelCatalog.from_file(args.root / 'catalog' / 'models.json')
    registry = ArtifactRegistry(args.root, catalog)
    config = load_pipeline_config(args.config, registry)
    ids = ([config.stage1.artifact_id] if config.stage1.enabled or args.use_stage1 else []) + [m.artifact_id for m in config.stage2.methods]
    output = {'valid_configuration': True, 'config_sha256': config.config_sha256,
              'manifest_sha256': {aid: registry.get(aid).manifest_sha256 for aid in ids},
              'selection': config.snapshot(), 'readiness': check_config_readiness(config, registry, include_stage1=config.stage1.enabled or args.use_stage1)}
    print(json.dumps(output, indent=2))
    return 1 if args.require_ready and not output['readiness']['ready'] else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        raise SystemExit(f'Invalid configuration: {exc}') from exc
