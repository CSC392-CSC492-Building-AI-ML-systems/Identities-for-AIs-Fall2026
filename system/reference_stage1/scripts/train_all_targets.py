#!/usr/bin/env python3
"""Train the saved response-only RF and Logistic Regression detector for each model.

By default, existing complete results are reused. For your current project,
pass `--exclude gemini-3.1-pro` to train just the other three models.
Results are aggregated without touching the final test partition.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from consolidation import safe_slug
from summarize_validation import discover_targets, create_reports


def complete_result(dest: Path, models: list[str]) -> bool:
    files = [dest / 'training_settings.json', dest / 'validation_metrics.csv']
    for choice in models:
        key = {'rf':'rf_stylometry', 'lr':'lr_tfidf'}[choice]
        files.extend([dest / f'{key}.joblib', dest / f'{key}_threshold.json',
                      dest / f'{key}_validation_predictions.csv'])
    return all(f.is_file() and f.stat().st_size > 0 for f in files)


def matches_current_dataset(dest: Path, target: str, data_root: Path, view: str) -> bool:
    """Don't silently treat an old fitted model as up to date after recollection."""
    from metrics_common import load_binary
    meta = json.loads((dest / 'training_settings.json').read_text(encoding='utf-8'))
    dev = load_binary(data_root, target, view, 'development')
    val = load_binary(data_root, target, view, 'validation')
    return (
        meta.get('target_model') == target and meta.get('view') == view
        and meta.get('training_rows') == len(dev)
        and meta.get('validation_rows') == len(val)
        and meta.get('development_prompts') == dev.prompt_id.nunique()
        and meta.get('validation_prompts') == val.prompt_id.nunique()
        and meta.get('negative_models_training') == sorted(dev.loc[dev.label == 0, 'model_key'].unique().tolist())
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('collector/data/supervised'))
    parser.add_argument('--results-root', type=Path, default=Path('collector/data/supervised_results'))
    parser.add_argument('--targets', nargs='+', help='Only train these exact model keys (default: all available)')
    parser.add_argument('--exclude', nargs='*', default=[], help='Do not train these targets, but include existing outputs in comparison')
    parser.add_argument('--models', nargs='+', choices=['rf', 'lr'], default=['rf', 'lr'])
    parser.add_argument('--view', default='all_personas')
    parser.add_argument('--max-false-alarm', type=float, default=0.10)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--force', action='store_true', help='Retrain even if saved results already exist')
    parser.add_argument('--comparison-out', type=Path, default=Path('collector/data/supervised_results/comparison'))
    args = parser.parse_args()

    available = discover_targets(args.data_root)
    requested = list(dict.fromkeys(args.targets or available))
    unknown = (set(requested) | set(args.exclude)) - set(available)
    if unknown:
        parser.error(f'Unknown model keys: {sorted(unknown)}; available: {available}')
    targets = [target for target in requested if target not in args.exclude]
    if not targets:
        parser.error('No targets to train after exclusions')
    selected = list(dict.fromkeys(args.models))
    print(f'Targets scheduled: {", ".join(targets)}', flush=True)
    print(f'Algorithms: {", ".join(selected)}', flush=True)
    trainer = Path(__file__).resolve().parent / 'train_baselines.py'
    for target in targets:
        dest = args.results_root / safe_slug(target) / args.view
        if not args.force and complete_result(dest, selected):
            if not matches_current_dataset(dest, target, args.data_root, args.view):
                raise RuntimeError(
                    f'Saved results for {target} do not match the current consolidated dataset. '
                    'Regenerate/review dataset and rerun with --force after deciding how to preserve the original results.'
                )
            print(f'REUSE {target}: complete validation outputs already exist', flush=True)
            continue
        command = [sys.executable, str(trainer), '--data-root', str(args.data_root),
                   '--results-root', str(args.results_root), '--target', target,
                   '--view', args.view, '--models', *selected,
                   '--seed', str(args.seed), '--max-false-alarm', str(args.max_false_alarm)]
        print(f'FIT {target} ...', flush=True)
        subprocess.run(command, check=True)
    # Include any existing results for excluded targets in the summary.
    report = create_reports(args.data_root, args.results_root, args.comparison_out,
                            args.view, tuple({'rf':'rf_stylometry','lr':'lr_tfidf'}[m] for m in selected),
                            require_all=False)
    print(f'\nSaved comparison report to: {report["out"].resolve()}')
    if report['missing']:
        print('Note: Some targets are still missing saved outputs; see report_manifest.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
