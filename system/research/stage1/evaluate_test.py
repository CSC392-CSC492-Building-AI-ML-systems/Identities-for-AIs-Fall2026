#!/usr/bin/env python3
"""Explicit final test evaluation of previously trained/frozen models.

Run only after examining validation results and choosing a method/threshold.
Loading joblib files is unsafe when they are from an untrusted source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import joblib
import pandas as pd
from consolidation import safe_slug
from metrics_common import load_binary, check_prompt_splits, score_metrics, prediction_rows, subgroup_metrics


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', type=Path, default=Path('system/.local/stage1/supervised'))
    p.add_argument('--results-root', type=Path, default=Path('system/.local/stage1/supervised_results'))
    p.add_argument('--target', required=True)
    p.add_argument('--view', default='all_personas')
    p.add_argument('--algorithm', choices=['rf_stylometry', 'lr_tfidf'], required=True)
    p.add_argument('--allow-overwrite', action='store_true')
    args = p.parse_args()

    dest = args.results_root / safe_slug(args.target) / args.view
    pred_path = dest / f'{args.algorithm}_test_predictions.csv'
    if pred_path.exists() and not args.allow_overwrite:
        raise ValueError(f'{pred_path} already exists; refusing to overwrite final results')
    meta = json.loads((dest / f'{args.algorithm}_threshold.json').read_text(encoding='utf-8'))
    if meta['target_model'] != args.target or meta['view'] != args.view or meta['algorithm'] != args.algorithm:
        raise ValueError('Saved threshold does not match requested target/view/algorithm')
    pipeline = joblib.load(dest / f'{args.algorithm}.joblib')
    dev = load_binary(args.data_root, args.target, args.view, 'development')
    val = load_binary(args.data_root, args.target, args.view, 'validation')
    test = load_binary(args.data_root, args.target, args.view, 'test')
    check_prompt_splits(dev, val, test)

    probs = pipeline.predict_proba(test['response_text'].astype(str).tolist())[:, 1]
    threshold = float(meta['threshold'])
    pred = prediction_rows(test, probs, threshold, args.algorithm, 'test')
    metrics = score_metrics(test['label'], probs, threshold, 'test', args.algorithm,
                            args.target, 'frozen_validation_threshold')
    pred.to_csv(pred_path, index=False)
    subgroup_metrics(pred, args.target).to_csv(dest / f'{args.algorithm}_test_by_group.csv', index=False)
    pd.DataFrame([metrics]).to_csv(dest / f'{args.algorithm}_test_metrics.csv', index=False)
    print(f'Final TEST ROC-AUC: {metrics["roc_auc"]:.3f}; '
          f'change detection rate: {metrics["change_detection_rate"]:.3f}; '
          f'false alarm rate: {metrics["false_alarm_rate"]:.3f}')
    print(f'Files: {dest.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
