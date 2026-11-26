"""Shared scoring methods for validation and untouched final test."""
from __future__ import annotations

from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, average_precision_score, confusion_matrix,
)


def load_binary(data_root: Path, target: str, view: str, split: str) -> pd.DataFrame:
    from consolidation import safe_slug
    path = data_root / 'binary' / safe_slug(target) / view / f'{split}.csv'
    if not path.is_file():
        raise FileNotFoundError(f'Missing {path}; run prepare_supervised_data.py first.')
    df = pd.read_csv(path, keep_default_na=False, dtype={'prompt_id': str, 'record_id': str})
    if df.empty:
        raise ValueError(f'No rows in {path}')
    required = {'response_text', 'label', 'prompt_id', 'record_id', 'model_key', 'prompt_category'}
    if not required.issubset(df.columns):
        raise ValueError(f'Missing columns in {path}: {sorted(required - set(df.columns))}')
    df['label'] = df['label'].astype(int)
    if set(df['label'].unique()) != {0, 1}:
        raise ValueError(f'Both binary classes are required in {path}')
    if not (df['label'] == (df['model_key'] == target).astype(int)).all():
        raise ValueError(f'Incorrect labels in {path}')
    if not df['record_id'].is_unique:
        raise ValueError(f'Duplicate record IDs in {path}')
    return df


def check_prompt_splits(dev: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame | None = None):
    if set(dev.prompt_id) & set(val.prompt_id):
        raise ValueError('Prompt IDs overlap between development and validation!')
    if test is not None and (set(test.prompt_id) & (set(dev.prompt_id) | set(val.prompt_id))):
        raise ValueError('Prompt IDs overlap with final test!')


def threshold_for_false_alarm_limit(y_true, scores, max_false_alarm=0.10) -> float:
    """Choose largest threshold keeping validation baseline false alarms <= max_false_alarm.

    A false alarm is a true baseline response labeled as 'changed': positive
    class mistakenly rejected (FN in standard binary target-model convention).
    """
    positive = np.sort(np.asarray(scores)[np.asarray(y_true) == 1])
    if len(positive) == 0:
        raise ValueError('No positive validation examples')
    idx = min(len(positive) - 1, int(math.floor(max_false_alarm * len(positive))))
    return float(positive[idx])


def score_metrics(y_true, scores, threshold: float, split: str, algorithm: str, target: str, rule: str) -> dict:
    y_true = np.asarray(y_true, dtype=int)
    scores = np.asarray(scores, dtype=float)
    pred = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel().tolist()
    m = {
        'split': split, 'algorithm': algorithm, 'target_model': target,
        'threshold_rule': rule, 'threshold': threshold,
        'n': len(y_true), 'positives': int(y_true.sum()), 'negatives': int((1 - y_true).sum()),
        'tp': tp, 'fn': fn, 'tn': tn, 'fp': fp,
        'accuracy': float(accuracy_score(y_true, pred)),
        'balanced_accuracy': float(balanced_accuracy_score(y_true, pred)),
        'precision_target': float(precision_score(y_true, pred, zero_division=0)),
        'recall_target': float(recall_score(y_true, pred, zero_division=0)),
        'f1_target': float(f1_score(y_true, pred, zero_division=0)),
        'false_alarm_rate': fn / (fn + tp) if (fn + tp) else float('nan'),
        'change_detection_rate': tn / (tn + fp) if (tn + fp) else float('nan'),
        'false_acceptance_rate': fp / (tn + fp) if (tn + fp) else float('nan'),
        'majority_negative_accuracy': float((y_true == 0).mean()),
        'roc_auc': float(roc_auc_score(y_true, scores)),
        'average_precision': float(average_precision_score(y_true, scores)),
    }
    return m


def prediction_rows(df: pd.DataFrame, scores, threshold: float, algo: str, split: str) -> pd.DataFrame:
    cols = ['record_id', 'prompt_id', 'model_key', 'prompt_category', 'persona_id', 'label']
    cols = [c for c in cols if c in df.columns]
    frame = df[cols].copy()
    frame['algorithm'] = algo
    frame['split'] = split
    frame['target_score'] = scores
    frame['predicted_target'] = (np.asarray(scores) >= threshold).astype(int)
    frame['threshold'] = threshold
    return frame


def subgroup_metrics(predictions: pd.DataFrame, target: str) -> pd.DataFrame:
    """Interpretive diagnostic summaries, not performance tuning on small groups."""
    out = []
    for name, key in [('prompt_category', 'prompt_category'), ('persona_id', 'persona_id')]:
        if key not in predictions.columns:
            continue
        for val, chunk in predictions.groupby(key):
            if chunk.label.nunique() < 2:
                continue
            out.append({
                'group_by': name, 'group': val, 'n': len(chunk),
                'target_recall': float(((chunk.label == 1) & (chunk.predicted_target == 1)).sum() / max(1,(chunk.label == 1).sum())),
                'change_detection_rate': float(((chunk.label == 0) & (chunk.predicted_target == 0)).sum() / max(1,(chunk.label == 0).sum())),
                'roc_auc': float(roc_auc_score(chunk.label, chunk.target_score)),
            })
    # For each alternative model, report rate of correctly rejecting it.
    for model, chunk in predictions[predictions.label == 0].groupby('model_key'):
        out.append({
            'group_by': 'negative_model', 'group': model, 'n': len(chunk),
            'target_recall': float('nan'),
            'change_detection_rate': float((chunk.predicted_target == 0).mean()),
            'roc_auc': float('nan'),
        })
    return pd.DataFrame(out, columns=['group_by','group','n','target_recall','change_detection_rate','roc_auc'])
