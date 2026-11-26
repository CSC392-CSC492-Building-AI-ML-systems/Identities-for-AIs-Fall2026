#!/usr/bin/env python3
"""Consolidate collector JSONL and prompt CSV into supervised-learning datasets.

Uses the same ingestion and category-stratified prompt splitting algorithm as the
previous Jev preparation script, without creating Jev reference sets.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

from consolidation import (
    read_prompts, load_responses, split_prompts, get_columns,
    write_csv, write_json, write_jsonl, safe_slug, view_name,
    SPLIT_NAMES, VIEW_ALL,
)

BINARY_COLUMNS = [
    'record_id', 'prompt_id', 'prompt_text', 'response_text',
    'prompt_category', 'persona_id', 'sample_index', 'model_key',
    'target_model', 'label', 'split', 'prompt_group', 'prompt_set_version',
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-dir', type=Path, default=Path('system/collector/data/raw'))
    p.add_argument('--prompts', type=Path, default=Path('system/collector/prompts/training_prompts.csv'))
    p.add_argument('--out', type=Path, default=Path('system/.local/stage1/supervised'))
    p.add_argument('--file-name', default='training_v1.jsonl')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--train-fraction', type=float, default=0.70)
    p.add_argument('--val-fraction', type=float, default=0.15)
    p.add_argument('--personas', nargs='*', default=['P13', 'BK1', 'P05'])
    p.add_argument('--expected-models', type=int, default=4)
    args = p.parse_args()

    if not 0 < args.train_fraction < 1 or not 0 < args.val_fraction < 1 or args.train_fraction + args.val_fraction >= 1:
        p.error('Both fractions must be positive and sum to less than 1.')
    if not args.raw_dir.is_dir():
        p.error(f'Missing raw-data directory: {args.raw_dir}')
    if not args.prompts.is_file():
        p.error(f'Missing prompt CSV: {args.prompts}')
    if args.out.resolve() == args.raw_dir.resolve():
        p.error('Output must be separate from raw input.')

    prompts = read_prompts(args.prompts)
    rows, source_info = load_responses(args.raw_dir, prompts, args.file_name)
    assignments = split_prompts(rows, args.seed, (
        args.train_fraction, args.val_fraction,
        1.0 - args.train_fraction - args.val_fraction,
    ))
    for row in rows:
        row['split'] = assignments[row['prompt_id']]
    models = sorted(source_info['models'])
    columns = get_columns(rows)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    write_csv(out / 'data' / 'all_responses.csv', rows, columns)
    write_jsonl(out / 'data' / 'all_responses.jsonl', rows)
    by_prompt = {r['prompt_id']: r for r in rows}
    assignment_rows = [
        {
            'prompt_id': pid,
            'split': assignments[pid],
            'prompt_category': by_prompt[pid]['prompt_category'],
            'persona_id': by_prompt[pid]['persona_id'],
        }
        for pid in sorted(assignments)
    ]
    write_csv(out / 'data' / 'prompt_assignments.csv', assignment_rows,
              ['prompt_id', 'split', 'prompt_category', 'persona_id'])
    views = {VIEW_ALL: None}
    for persona in args.personas:
        persona = persona.strip()
        if persona:
            views[view_name(persona)] = persona

    for view, persona in views.items():
        sub = [r for r in rows if persona is None or r['persona_id'] == persona]
        for split in SPLIT_NAMES:
            part = [r for r in sub if r['split'] == split]
            write_csv(out / 'views' / view / f'{split}.csv', part, columns)
            if view == VIEW_ALL:
                write_csv(out / 'splits' / f'{split}.csv', part, columns)
            for target in models:
                binaries = [
                    {**r, 'target_model': target, 'label': int(r['model_key'] == target)}
                    for r in part
                ]
                write_csv(out / 'binary' / safe_slug(target) / view / f'{split}.csv',
                          binaries, BINARY_COLUMNS)

    # Strict leakage check, independent of any downstream training script.
    split_prompts_seen = {
        split: {pid for pid, s in assignments.items() if s == split}
        for split in SPLIT_NAMES
    }
    for ix, name in enumerate(SPLIT_NAMES):
        for other in SPLIT_NAMES[ix + 1:]:
            if split_prompts_seen[name] & split_prompts_seen[other]:
                raise AssertionError(f'Prompt leakage: {name} vs. {other}')

    warnings = []
    if len(models) < args.expected_models:
        warnings.append(f'Only {len(models)} models found (expected {args.expected_models})')
    if source_info['metadata_disagreements']:
        warnings.append('JSONL/CSV metadata disagreements: prompt CSV metadata took precedence')
    if source_info['stats'].get('skipped_empty_responses'):
        warnings.append(f"Skipped {source_info['stats']['skipped_empty_responses']} empty responses")
    if source_info['stats'].get('skipped_errors'):
        warnings.append(f"Skipped {source_info['stats']['skipped_errors']} errored records")
    summary = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'seed': args.seed,
        'raw_dir': str(args.raw_dir),
        'prompt_csv': str(args.prompts),
        'source_files': source_info['sources'],
        'models': models,
        'model_counts': dict(sorted(Counter(r['model_key'] for r in rows).items())),
        'unique_prompts': len(assignments),
        'prompts_by_split': dict(Counter(assignments.values())),
        'responses_by_split': dict(Counter(r['split'] for r in rows)),
        'load_stats': source_info['stats'],
        'metadata_disagreements': source_info['metadata_disagreements'],
        'views': {name: persona for name, persona in views.items()},
        'methodology': {
            'split_unit': 'prompt_id; all models and repetitions remain together',
            'stratified_by': 'prompt_category',
            'splitting_algorithm': 'same deterministic SHA-256-seeded category shuffles as Jev preparation',
            'positive_label': '1 = target model, 0 = another known model',
            'features': 'to be extracted from response_text only by supervised training scripts',
            'test_policy': 'freeze models/thresholds before running evaluate_test.py',
        },
        'warnings': warnings,
    }
    write_json(out / 'summary.json', summary)
    print(f'Models: {models}')
    print(f'Rows: {len(rows)}; prompts: {len(assignments)}')
    print(f'Prompts by split: {summary["prompts_by_split"]}')
    print(f'Responses by split: {summary["responses_by_split"]}')
    print(f'Output: {out.resolve()}')
    for msg in warnings:
        print('WARNING:', msg, file=sys.stderr)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
