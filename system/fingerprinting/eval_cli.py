"""Unified offline evaluation CLI for Stage 1, standalone Stage 2 and E2E.

Example (from GitHub repo root):
  python -m fingerprinting.eval_cli --rf-pilot --limit-per-model 3 --scope all
  python -m fingerprinting.eval_cli --rf-pilot --scope e2e --methods random_forest
  python -m fingerprinting.eval_cli --cases path/to/cases.jsonl --scope all

Mock Harness is for wiring/rules tests only, NOT live judge accuracy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters.builders import real_adapter_constructors
from .config import load_pipeline_config
from .eval_cases import (convert_rf_holdout, read_cases, source_sha256,
                         write_cases)
from .eval_suite import run_suite, save_suite
from .factory import PipelineFactory
from .model_catalog import ModelCatalog
from .registry import ArtifactRegistry


def main(argv: list[str] | None = None) -> int:
    root_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument('--cases', type=Path, help='Normalized evaluation JSONL from the specified dataset')
    sources.add_argument('--rf-pilot', action='store_true', help='Convert bundled original RF P13 holdout to PILOT swap/unchanged cases')
    parser.add_argument('--root', type=Path, default=root_default, help='Project root containing catalog/ and models/')
    parser.add_argument('--config', type=Path, default=None, help='Pipeline YAML; default config/production.yaml')
    parser.add_argument('--scope', choices=('stage1','stage2','e2e','all'), default='all')
    parser.add_argument('--methods', default=None, help='Comma-separated subset/order of lora,harness,random_forest')
    parser.add_argument('--stage2-mode', choices=('single','fallback','run_all'), default=None)
    parser.add_argument('--all-stage1-approaches', action='store_true')
    stage1_switch = parser.add_mutually_exclusive_group()
    stage1_switch.add_argument('--use-stage1', dest='use_stage1', action='store_true', default=None, help='Opt into Stage 1 for end-to-end evaluation')
    stage1_switch.add_argument('--no-stage1', dest='use_stage1', action='store_false', help='Force Stage 1 off for end-to-end evaluation')
    parser.add_argument('--allow-partial-e2e', action='store_true', help='Explicitly permit subset of ready Stage 2 methods if some selected weights are missing')
    parser.add_argument('--judge-provider', choices=('mock','google','anthropic','openai'), default='mock')
    parser.add_argument('--allow-live-judge', action='store_true', help='Required for API judge calls; costs money and sends responses externally')
    parser.add_argument('--limit', type=int, default=None, help='Limit the number of externally supplied JSONL cases')
    parser.add_argument('--limit-per-model', type=int, default=4, help='RF pilot samples per actual model; 0 uses all (not prompt-diverse)')
    parser.add_argument('--output', type=Path, default=None, help='Output directory; defaults to reports/unified_pilot or reports/unified_run')
    args = parser.parse_args(argv)
    if args.judge_provider != 'mock' and not args.allow_live_judge:
        parser.error('Real Harness judge requires --allow-live-judge and valid provider credentials')
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if args.limit_per_model < 0:
        parser.error('--limit-per-model must be nonnegative')
    root = args.root.resolve()
    catalog = ModelCatalog.from_file(root/'catalog/models.json')
    registry = ArtifactRegistry(root, catalog)
    cfg = load_pipeline_config(args.config or root/'config/production.yaml', registry)
    methods = args.methods.split(',') if args.methods else None
    if methods is not None:
        methods = [x.strip() for x in methods]
    if args.rf_pilot:
        path = root/'testdata/random_forest/heldout_raw_cases.jsonl'
        cases = convert_rf_holdout(path, catalog, limit_per_model=args.limit_per_model)
        source_type = 'rf_fixed_prompt_holdout_P13:paired_scenarios_NOT_independent'
    else:
        path = args.cases.resolve()
        cases = read_cases(path, catalog, limit=args.limit)
        source_type = 'user_supplied_normalized_jsonl'
    output = args.output or root/'reports'/('unified_pilot' if args.rf_pilot else 'unified_run')
    constructors = real_adapter_constructors(harness_judge_provider=args.judge_provider)
    factory = PipelineFactory(registry, constructors, require_ready=True)
    suite = run_suite(cases, cfg, registry, factory, scope=args.scope,
                      methods=methods, stage2_mode=args.stage2_mode,
                      allow_partial_e2e=args.allow_partial_e2e,
                      judge_provider=args.judge_provider,
                      run_all_stage1_approaches=args.all_stage1_approaches,
                      use_stage1=args.use_stage1)
    suite['dataset']['source_type'] = source_type
    suite['dataset']['source_file'] = path.name
    save_suite(suite, output, dataset_source=path.name, dataset_sha256=source_sha256(path))
    print(f'Wrote evaluation reports to {output.resolve()}')
    for name, report in suite['reports'].items():
        m = report['metrics']
        value = (m.get('candidate_top1_accuracy_on_supported_with_candidate')
                 if name.startswith('stage2/') else
                 m.get('end_to_end_exact_model_accuracy', m.get('verification_decision_accuracy')))
        label = 'supported_top1_candidate_accuracy' if name.startswith('stage2/') else 'final_decision_accuracy'
        print(f'  {name}: {report["status"]}; {m.get("n_cases")} cases; {label}={value}')
    for name, reason in suite['blocked'].items():
        print(f'  BLOCKED {name}: {reason}')
    if not suite['reports']:
        print('No scopes completed. See summary.md and root TBD.md for prerequisites.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
