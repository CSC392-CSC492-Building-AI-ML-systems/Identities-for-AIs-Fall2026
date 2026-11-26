#!/usr/bin/env python3
"""Fairly compare within-family vs old one-vs-rest *on identical validation rows*.

The old model's metrics are re-computed on just its sibling-model negatives,
not copied from its 3-negative-model summary. Both models retain their
validation-selected thresholds. This is exploratory, not final test evaluation.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from metrics_common import score_metrics

REQUIRED = {'target_model','record_id','prompt_id','model_key','label',
            'algorithm','threshold_rule','threshold','target_score'}
RULES = ['fixed_0.5','validation_false_alarm_limit']


def load_predictions(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f'File not found: {path}')
    df = pd.read_csv(path,dtype={'record_id':str,'prompt_id':str},keep_default_na=False)
    missing = REQUIRED-set(df.columns)
    if missing:
        raise ValueError(f'Missing columns in {path}: {sorted(missing)}')
    if df.empty:
        raise ValueError(f'Empty predictions: {path}')
    df['label']=pd.to_numeric(df.label,errors='raise').astype(int)
    df['threshold']=pd.to_numeric(df.threshold,errors='raise')
    df['target_score']=pd.to_numeric(df.target_score,errors='raise')
    if (df.target_score.lt(0) | df.target_score.gt(1) | ~np.isfinite(df.target_score)).any():
        raise ValueError(f'Invalid target scores in {path}')
    if not df['label'].eq(df.model_key.eq(df.target_model).astype(int)).all():
        raise ValueError(f'Labels inconsistent with target_model in {path}')
    if df.duplicated(['target_model','algorithm','threshold_rule','record_id']).any():
        raise ValueError(f'Duplicate prediction identity in {path}')
    return df


def joined_pair(within:pd.DataFrame, old:pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    if within['sibling_model'].nunique()!=1:
        raise ValueError('Within group must correspond to one sibling model')
    sibling=within['sibling_model'].iloc[0]
    target=within['target_model'].iloc[0]
    if target==sibling:
        raise ValueError('Target and sibling must differ')
    if set(within.model_key)!={target,sibling}:
        raise ValueError(f'Within-family predictions contain unexpected models for {target}')
    old_filtered=old[old.model_key.isin([target,sibling])].copy()
    keys=['record_id','prompt_id','model_key','label']
    if within.duplicated('record_id').any() or old_filtered.duplicated('record_id').any():
        raise ValueError('Repeated record ID within a single target/algorithm/rule')
    a=within.set_index('record_id')
    b=old_filtered.set_index('record_id')
    if set(a.index)!=set(b.index):
        missing_old=set(a.index)-set(b.index)
        missing_new=set(b.index)-set(a.index)
        raise ValueError(
            f'Prediction datasets disagree for {target}: '
            f'{len(missing_old)} pairwise IDs missing old, '
            f'{len(missing_new)} old IDs missing pairwise. '
            'Consolidate and train from the same source/split before comparing.'
        )
    b=b.loc[a.index]
    for key in ['prompt_id','model_key','label']:
        if not a[key].astype(str).eq(b[key].astype(str)).all():
            raise ValueError(f'Inconsistent {key} between new and old results')
    if within.prompt_id.nunique()<5:
        print(f'WARNING: only {within.prompt_id.nunique()} distinct validation prompts')
    return within,old_filtered


def per_prompt_stats(df:pd.DataFrame)->dict:
    g=df.groupby(['prompt_id','label'])['target_score'].mean().unstack()
    if 0 not in g or 1 not in g:
        return {'matched_prompts':0,'prompt_win_rate':float('nan'),
                'mean_prompt_score_margin':float('nan')}
    g=g.dropna(subset=[0,1])
    margins=g[1]-g[0]
    return {'matched_prompts':len(margins),
            'prompt_win_rate':float((margins>0).mean()),
            'mean_prompt_score_margin':float(margins.mean())}


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--within',type=Path,
        default=Path('system/.local/stage1/within_family_results/comparison/all_within_family_validation_predictions.csv'))
    ap.add_argument('--ovr',type=Path,
        default=Path('system/.local/stage1/supervised_results/comparison/all_validation_predictions.csv'))
    ap.add_argument('--out',type=Path,
        default=Path('system/.local/stage1/within_family_results/comparison'))
    args=ap.parse_args()
    within=load_predictions(args.within)
    if 'sibling_model' not in within or 'family' not in within:
        raise ValueError('Within-family prediction file must contain family and sibling_model')
    ovr=load_predictions(args.ovr)
    result=[]
    for (target,algo,rule),sub in within.groupby(['target_model','algorithm','threshold_rule'],sort=True):
        if rule not in RULES:
            continue
        others=ovr[(ovr.target_model==target)&(ovr.algorithm==algo)&(ovr.threshold_rule==rule)]
        if others.empty:
            raise ValueError(f'Old predictions missing {target}, {algo}, {rule}')
        pair,old_pair=joined_pair(sub,others)
        for approach,df in [('within_family',pair),('one_vs_rest',old_pair)]:
            thresholds=df.threshold.unique()
            if len(thresholds)!=1:
                raise ValueError(f'Inconsistent thresholds in {approach} {target} {algo} {rule}')
            metrics=score_metrics(df.label.to_numpy(int),df.target_score.to_numpy(float),
                                  float(thresholds[0]),'validation',algo,target,rule)
            stats=per_prompt_stats(df)
            metrics.update({'approach':approach,'family':sub.family.iloc[0],
                            'sibling_model':sub.sibling_model.iloc[0],**stats})
            result.append(metrics)
    output=pd.DataFrame(result)
    if output.empty:
        raise ValueError('No matching model comparisons found')
    args.out.mkdir(parents=True,exist_ok=True)
    output.sort_values(['family','target_model','algorithm','threshold_rule','approach']).to_csv(
        args.out/'fair_pairwise_vs_ovr_metrics.csv',index=False)
    id_cols=['family','target_model','sibling_model','algorithm','threshold_rule']
    keys=['roc_auc','accuracy','false_alarm_rate','change_detection_rate',
          'false_acceptance_rate','prompt_win_rate','mean_prompt_score_margin']
    a=output[output.approach=='within_family'][id_cols+keys].set_index(id_cols)
    b=output[output.approach=='one_vs_rest'][id_cols+keys].set_index(id_cols)
    if set(a.index)!=set(b.index):
        raise AssertionError('Model comparator mismatch')
    diff=a-b.loc[a.index]
    diff.columns=[f'{col}_delta_pairwise_minus_ovr' for col in diff.columns]
    diff.reset_index().to_csv(args.out/'pairwise_improvement_deltas.csv',index=False)
    print(f'Compared {len(diff)} exact-match target/algorithm/threshold conditions.')
    print(f'Saved fair comparison to {args.out.resolve()}')
    print('IMPORTANT: OVR performance here is restricted to the SAME target/sibling responses.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
