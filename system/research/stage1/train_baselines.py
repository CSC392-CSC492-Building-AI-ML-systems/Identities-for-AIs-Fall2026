#!/usr/bin/env python3
"""Train response-only one-vs-rest RF and TF-IDF Logistic Regression baselines.

Training sees DEVELOPMENT only. Validation is used to compare classifiers and
select a threshold. The final test partition is never read by this program.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from consolidation import safe_slug
from metrics_common import (
    load_binary, check_prompt_splits, threshold_for_false_alarm_limit,
    score_metrics, prediction_rows, subgroup_metrics,
)
from stylometry import StylometryTransformer, FEATURE_NAMES


def make_random_forest(seed: int) -> Pipeline:
    return Pipeline([
        ('style', StylometryTransformer()),
        ('imputer', SimpleImputer(strategy='median')),
        ('classifier', RandomForestClassifier(
            n_estimators=300, max_features='sqrt',
            min_samples_leaf=2, class_weight='balanced_subsample',
            random_state=seed, n_jobs=-1,
        )),
    ])


def make_tfidf_lr(seed: int) -> Pipeline:
    return Pipeline([
        ('tfidf', FeatureUnion([
            ('word', TfidfVectorizer(
                analyzer='word', ngram_range=(1, 2), min_df=2,
                max_features=35000, sublinear_tf=True, strip_accents='unicode',
            )),
            ('char', TfidfVectorizer(
                analyzer='char', ngram_range=(3, 5), min_df=2,
                max_features=65000, sublinear_tf=True, strip_accents='unicode',
            )),
        ])),
        ('classifier', LogisticRegression(
            C=1.0, class_weight='balanced', solver='liblinear',
            max_iter=1500, random_state=seed,
        )),
    ])


def write_importances(pipeline: Pipeline, model_key: str, out: Path):
    if model_key == 'rf_stylometry':
        importance = pipeline.named_steps['classifier'].feature_importances_
        pd.DataFrame({'feature': FEATURE_NAMES, 'importance': importance}).sort_values(
            'importance', ascending=False
        ).to_csv(out / 'rf_feature_importance.csv', index=False)
    if model_key == 'lr_tfidf':
        union = pipeline.named_steps['tfidf']
        names = union.get_feature_names_out()
        weights = pipeline.named_steps['classifier'].coef_[0]
        tbl = pd.DataFrame({'feature': names, 'coefficient': weights})
        head = pd.concat([tbl.nlargest(30, 'coefficient'), tbl.nsmallest(30, 'coefficient')])
        head.to_csv(out / 'lr_top_coefficients.csv', index=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root', type=Path, default=Path('system/.local/stage1/supervised'))
    ap.add_argument('--target', required=True, help='Exact model key, e.g. gemini-3.1-pro')
    ap.add_argument('--view', default='all_personas', help='all_personas or persona_P13')
    ap.add_argument('--results-root', type=Path, default=Path('system/.local/stage1/supervised_results'))
    ap.add_argument('--models', nargs='+', choices=['rf', 'lr'], default=['rf', 'lr'])
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--max-false-alarm', type=float, default=0.10,
                    help='Allow this fraction of genuine target responses to be flagged on validation')
    args = ap.parse_args()

    if not 0 <= args.max_false_alarm < 1:
        ap.error('--max-false-alarm must be between 0 (inclusive) and 1 (exclusive)')
    dev = load_binary(args.data_root, args.target, args.view, 'development')
    val = load_binary(args.data_root, args.target, args.view, 'validation')
    check_prompt_splits(dev, val)
    if dev['response_text'].isna().any() or val['response_text'].isna().any():
        raise ValueError('Missing response text; re-run consolidation')

    out = args.results_root / safe_slug(args.target) / args.view
    out.mkdir(parents=True, exist_ok=True)

    X_train = dev['response_text'].astype(str).tolist()
    X_val = val['response_text'].astype(str).tolist()
    y_train = dev['label'].to_numpy(dtype=int)
    y_val = val['label'].to_numpy(dtype=int)
    constructors = {'rf': ('rf_stylometry', make_random_forest),
                    'lr': ('lr_tfidf', make_tfidf_lr)}
    metrics = []
    for choice in dict.fromkeys(args.models):
        model_key, constructor = constructors[choice]
        print(f'Training {model_key}: {args.target} vs the other models ...', flush=True)
        pipeline = constructor(args.seed)
        pipeline.fit(X_train, y_train)
        scores = pipeline.predict_proba(X_val)[:, 1]
        threshold = threshold_for_false_alarm_limit(y_val, scores, args.max_false_alarm)
        for rule, t in [('fixed_0.5', 0.5), ('validation_false_alarm_limit', threshold)]:
            metrics.append(score_metrics(y_val, scores, t, 'validation', model_key, args.target, rule))
        pred = prediction_rows(val, scores, threshold, model_key, 'validation')
        pred.to_csv(out / f'{model_key}_validation_predictions.csv', index=False)
        subgroup_metrics(pred, args.target).to_csv(out / f'{model_key}_validation_by_group.csv', index=False)
        write_importances(pipeline, model_key, out)
        joblib.dump(pipeline, out / f'{model_key}.joblib', compress=3)
        (out / f'{model_key}_threshold.json').write_text(json.dumps({
            'algorithm': model_key, 'target_model': args.target, 'view': args.view,
            'threshold': threshold, 'selection': 'validation_false_alarm_limit',
            'max_false_alarm': args.max_false_alarm, 'seed': args.seed,
        }, indent=2) + '\n', encoding='utf-8')
        print(f'  Validation ROC-AUC: {metrics[-1]["roc_auc"]:.3f}; '
              f'change detection: {metrics[-1]["change_detection_rate"]:.3f}; '
              f'false alarms: {metrics[-1]["false_alarm_rate"]:.3f}', flush=True)

    pd.DataFrame(metrics).to_csv(out / 'validation_metrics.csv', index=False)
    settings = {
        'trained_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_model': args.target, 'view': args.view,
        'models': list(dict.fromkeys(args.models)),
        'seed': args.seed,
        'training_rows': len(dev), 'validation_rows': len(val),
        'development_prompts': dev.prompt_id.nunique(),
        'validation_prompts': val.prompt_id.nunique(),
        'positive_training': int(y_train.sum()), 'negative_training': int((1 - y_train).sum()),
        'negative_models_training': sorted(dev.loc[dev.label == 0, 'model_key'].unique().tolist()),
        'training_input_columns': ['response_text'],
        'label_rule': '1 if model_key equals target_model, else 0',
        'threshold_selection': 'validation only; maximum 10% baseline false alarm unless overridden',
        'note': 'No test data was read. Do not change settings after final test evaluation.',
        'versions': {'sklearn': sklearn.__version__, 'numpy': np.__version__, 'pandas': pd.__version__},
    }
    (out / 'training_settings.json').write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
    print(f'Validation results saved to {out.resolve()}')
    print('Final test remains untouched. Evaluate only after model/threshold choice is frozen.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
