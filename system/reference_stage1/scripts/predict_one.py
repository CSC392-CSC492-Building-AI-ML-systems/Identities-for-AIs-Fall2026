#!/usr/bin/env python3
"""Classify ONE new response from a saved baseline detector (no reference examples)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import joblib


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True, help='Saved rf_stylometry.joblib or lr_tfidf.joblib')
    p.add_argument('--threshold-file', type=Path, required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--response-file', type=Path, help='UTF-8 text file containing new response')
    group.add_argument('--response', type=str, help='New response pasted on command line')
    args = p.parse_args()
    text = args.response_file.read_text(encoding='utf-8') if args.response_file else args.response
    info = json.loads(args.threshold_file.read_text(encoding='utf-8'))
    model = joblib.load(args.model)  # Only load models created by your own trusted training run.
    score = float(model.predict_proba([text])[:, 1][0])
    accepted = score >= float(info['threshold'])
    print(json.dumps({
        'target_model': info['target_model'],
        'target_score': round(score, 6),
        'threshold': info['threshold'],
        'prediction': 'consistent_with_baseline' if accepted else 'possible_model_change',
        'interpretation': 'Evidence of response similarity, not proof of model identity',
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
