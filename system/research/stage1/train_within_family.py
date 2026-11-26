#!/usr/bin/env python3
"""Train response-only, within-family one-vs-one LLM detectors.

Trains separately for each target orientation so its score directly means
P(response belongs to that named target, among the two compared models).
Development trains; validation selects thresholds; test is never read.

Usage:
  python system/research/stage1/train_within_family.py --families gemini llama
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from consolidation import safe_slug
from metrics_common import check_prompt_splits, score_metrics, threshold_for_false_alarm_limit
from train_baselines import make_random_forest, make_tfidf_lr, write_importances

FAMILIES = {
    'gemini': ('gemini-3.1-pro', 'gemini-3.8-flash'),
    'llama': ('llama3.1-8b', 'llama3.2-3b'),
}
ALGORITHMS = {
    'rf': ('rf_stylometry', make_random_forest),
    'lr': ('lr_tfidf', make_tfidf_lr),
}
REQUIRED = {'record_id', 'prompt_id', 'model_key', 'response_text', 'prompt_category', 'persona_id'}


def load_split(root: Path, view: str, split: str) -> pd.DataFrame:
    path = root / 'views' / view / f'{split}.csv'
    if not path.is_file():
        raise FileNotFoundError(f'Missing {path}. Run prepare_supervised_data.py first.')
    df = pd.read_csv(path, dtype={'record_id': str, 'prompt_id': str}, keep_default_na=False)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f'Missing required columns in {path}: {sorted(missing)}')
    if df.empty or not df['record_id'].is_unique:
        raise ValueError(f'Empty dataset or duplicate record IDs in {path}')
    if df.response_text.astype(str).str.strip().eq('').any():
        raise ValueError(f'Empty response_text in {path}')
    return df


def select_pair(df: pd.DataFrame, target: str, sibling: str) -> pd.DataFrame:
    pair = df[df.model_key.isin([target, sibling])].copy()
    pair['label'] = (pair.model_key == target).astype(int)
    if set(pair['label']) != {0, 1}:
        raise ValueError(f'Both target {target} and sibling {sibling} must have responses in every split')
    return pair


def make_pred_rows(df: pd.DataFrame, scores: np.ndarray, algo: str,
                   family: str, target: str, sibling: str, threshold: float,
                   rule: str) -> pd.DataFrame:
    cols = ['record_id','prompt_id','model_key','prompt_category','persona_id','label']
    if 'sample_index' in df:
        cols.append('sample_index')
    out = df[cols].copy()
    out.insert(0, 'target_model', target)
    out.insert(1, 'family', family)
    out.insert(2, 'sibling_model', sibling)
    out['algorithm'] = algo
    out['threshold_rule'] = rule
    out['threshold'] = float(threshold)
    out['target_score'] = scores
    out['predicted_target'] = (scores >= threshold).astype(int)
    out['correct'] = (out['label'] == out['predicted_target']).astype(int)
    return out


def per_prompt_ranking(df: pd.DataFrame, scores: np.ndarray,
                       family: str, target: str, sibling: str, algo: str) -> pd.DataFrame:
    tmp = df[['prompt_id','label']].copy()
    tmp['score'] = np.asarray(scores)
    grouped = tmp.groupby(['prompt_id', 'label']).agg(
        score_mean=('score', 'mean'), response_count=('score','size')
    ).reset_index()
    s = grouped.pivot(index='prompt_id', columns='label', values='score_mean')
    n = grouped.pivot(index='prompt_id', columns='label', values='response_count')
    if 0 not in s.columns or 1 not in s.columns:
        return pd.DataFrame()
    matched = s[[0,1]].dropna()
    out = pd.DataFrame({
        'family': family, 'target_model': target, 'sibling_model': sibling,
        'algorithm': algo, 'prompt_id': matched.index,
        'target_mean_score': matched[1].to_numpy(),
        'sibling_mean_score': matched[0].to_numpy(),
        'target_responses': n.loc[matched.index,1].to_numpy(dtype=int),
        'sibling_responses': n.loc[matched.index,0].to_numpy(dtype=int),
    })
    out['score_margin'] = out['target_mean_score'] - out['sibling_mean_score']
    out['target_ranked_higher'] = (out['score_margin'] > 0).astype(int)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root', type=Path, default=Path('system/.local/stage1/supervised'))
    ap.add_argument('--out', type=Path, default=Path('system/.local/stage1/within_family_results'))
    ap.add_argument('--view', default='all_personas')
    ap.add_argument('--families', nargs='+', choices=list(FAMILIES), default=list(FAMILIES))
    ap.add_argument('--algorithms', nargs='+', choices=list(ALGORITHMS), default=list(ALGORITHMS))
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--max-false-alarm', type=float, default=0.10,
                    help='Maximum fraction of true target responses rejected on validation')
    args = ap.parse_args()
    if not 0 <= args.max_false_alarm < 1:
        ap.error('--max-false-alarm must be in [0,1)')
    out = args.out
    dev = load_split(args.data_root, args.view, 'development')
    val = load_split(args.data_root, args.view, 'validation')
    check_prompt_splits(dev,val)
    metrics_rows, predictions, paired = [], [], []
    summaries = []
    for family in dict.fromkeys(args.families):
        a, b = FAMILIES[family]
        for target, sibling in [(a,b),(b,a)]:
            train_df = select_pair(dev,target,sibling)
            val_df = select_pair(val,target,sibling)
            target_out = out / family / safe_slug(target) / args.view
            target_out.mkdir(parents=True, exist_ok=True)
            print(f'\n{family}: {target} (1) vs {sibling} (0)', flush=True)
            print(f'  dev={len(train_df)} val={len(val_df)}; prompts dev/val='
                  f'{train_df.prompt_id.nunique()}/{val_df.prompt_id.nunique()}', flush=True)
            X_dev = train_df.response_text.astype(str).tolist()
            X_val = val_df.response_text.astype(str).tolist()
            y_dev = train_df.label.to_numpy(int)
            y_val = val_df.label.to_numpy(int)
            if len(np.unique(y_dev)) != 2 or len(np.unique(y_val)) != 2:
                raise ValueError('Missing class within a family partition')
            local_metrics = []
            for choice in dict.fromkeys(args.algorithms):
                name, constructor = ALGORITHMS[choice]
                print(f'  Training {name}...', flush=True)
                model = constructor(args.seed)
                model.fit(X_dev,y_dev)
                scores = model.predict_proba(X_val)[:,1]
                threshold = threshold_for_false_alarm_limit(y_val, scores, args.max_false_alarm)
                for rule,t in [('fixed_0.5',0.5),('validation_false_alarm_limit',threshold)]:
                    metrics = score_metrics(y_val,scores,t,'validation',name,target,rule)
                    metrics.update({'family': family,'sibling_model':sibling,
                                    'training_responses': len(train_df),
                                    'validation_prompts': val_df.prompt_id.nunique()})
                    local_metrics.append(metrics)
                    metrics_rows.append(metrics)
                    predictions.append(make_pred_rows(val_df,scores,name,family,target,sibling,t,rule))
                ranks = per_prompt_ranking(val_df,scores,family,target,sibling,name)
                if not ranks.empty:
                    paired.append(ranks)
                joblib.dump(model,target_out/f'{name}.joblib',compress=3)
                write_importances(model,name,target_out)
                (target_out/f'{name}_threshold.json').write_text(json.dumps({
                    'family':family,'target_model':target,'sibling_model':sibling,
                    'algorithm':name,'threshold':threshold,
                    'max_false_alarm':args.max_false_alarm,
                    'selection':'validation_false_alarm_limit',
                    'positive_label':'target_model',
                    'note':'Valid conditional on two known models from this family, not an open-set detector',
                },indent=2)+'\n',encoding='utf-8')
                print(f'    AUC={roc_auc_score(y_val,scores):.3f}; threshold@FA≤{args.max_false_alarm:.0%}={threshold:.3f}',flush=True)
            pd.DataFrame(local_metrics).to_csv(target_out/'validation_metrics.csv',index=False)
            summaries.append({'family':family,'target_model':target,'sibling_model':sibling,
                              'training_rows':len(train_df),'validation_rows':len(val_df),
                              'positive_dev':int(y_dev.sum()),'negative_dev':int((1-y_dev).sum()),
                              'development_prompts':train_df.prompt_id.nunique(),
                              'validation_prompts':val_df.prompt_id.nunique()})
    comp_dir = out/'comparison'
    comp_dir.mkdir(parents=True,exist_ok=True)
    pred = pd.concat(predictions,ignore_index=True)
    pred.to_csv(comp_dir/'all_within_family_validation_predictions.csv',index=False)
    pd.DataFrame(metrics_rows).to_csv(comp_dir/'within_family_validation_metrics.csv',index=False)
    pairs = pd.concat(paired,ignore_index=True) if paired else pd.DataFrame()
    pairs.to_csv(comp_dir/'within_family_prompt_ranking.csv',index=False)
    if not pairs.empty:
        agg = pairs.groupby(['family','target_model','sibling_model','algorithm']).agg(
            matched_prompts=('prompt_id','nunique'),
            target_higher_prompts=('target_ranked_higher','sum'),
            mean_prompt_score_margin=('score_margin','mean')
        ).reset_index()
        agg['prompt_win_rate'] = agg.target_higher_prompts / agg.matched_prompts
        agg.to_csv(comp_dir/'within_family_prompt_summary.csv',index=False)
    (comp_dir/'run_manifest.json').write_text(json.dumps({
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'source':str(args.data_root),'view':args.view,'seed':args.seed,
        'families':[f for f in dict.fromkeys(args.families)],
        'algorithms':[a for a in dict.fromkeys(args.algorithms)],
        'threshold_max_false_alarm':args.max_false_alarm,
        'targets':summaries,
        'methodology':{
            'train':'development responses only',
            'validate':'validation responses only, same old prompt partition',
            'test':'not opened',
            'positive_class':'target model only',
            'negative_class':'other model of same family only',
            'features':'response_text only, prompt text and persona labels excluded',
            'confidence':'AUC and threshold metrics are validation estimates; repeat responses within prompts are correlated',
            'scope':'Two known-model conditional discrimination, not unseen replacement detection',
        },
    },indent=2)+'\n',encoding='utf-8')
    print(f'\nSaved to {comp_dir.resolve()}')
    print('No final test rows were accessed.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
