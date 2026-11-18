"""Experiment 5 utilities: reproducible response-only evaluation on validation.
No test files are opened here.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from metrics_common import score_metrics, threshold_for_false_alarm_limit

FAMILIES = {
    'gemini': ('gemini-3.1-pro', 'gemini-3.8-flash'),
    'llama': ('llama3.1-8b', 'llama3.2-3b'),
}
MODEL_TO_FAMILY = {model: family for family, models in FAMILIES.items() for model in models}


def load_data(root: Path, view: str):
    dfs=[]
    for split in ['development','validation']:
        p=root/'views'/view/f'{split}.csv'
        if not p.exists():
            raise FileNotFoundError(f'Missing {p}; run prepare_supervised_data.py first.')
        df=pd.read_csv(p, dtype={'record_id':str,'prompt_id':str},keep_default_na=False)
        needed={'record_id','prompt_id','model_key','response_text','prompt_category','persona_id'}
        if needed-set(df.columns):
            raise ValueError(f'Missing columns in {p}: {needed-set(df.columns)}')
        if not df.record_id.is_unique:
            raise ValueError(f'Duplicate record_ids in {p}')
        if df.response_text.astype(str).str.strip().eq('').any():
            raise ValueError(f'Empty response_text in {p}')
        dfs.append(df)
    dev,val=dfs
    if set(dev.prompt_id)&set(val.prompt_id):
        raise ValueError('Prompt leakage across development and validation!')
    expected=set(MODEL_TO_FAMILY)
    if not expected.issubset(set(dev.model_key)) or not expected.issubset(set(val.model_key)):
        raise ValueError(f'Expected all 4 models in both splits. Missing development={expected-set(dev.model_key)}, validation={expected-set(val.model_key)}')
    # Extra models may be present, but are excluded from these specifically four-model experiments.
    return dev[dev.model_key.isin(expected)].copy(),val[val.model_key.isin(expected)].copy()


def make_pred(df, score, target, algo, approach, threshold, rule):
    out=df[['record_id','prompt_id','prompt_category','persona_id','model_key']].copy()
    out['target_model']=target
    out['family']=MODEL_TO_FAMILY[target]
    out['algorithm']=algo
    out['approach']=approach
    out['label']=(out.model_key==target).astype(int)
    out['target_score']=np.asarray(score,dtype=float)
    out['threshold_rule']=rule
    out['threshold']=float(threshold)
    out['predicted_target']=(out.target_score>=threshold).astype(int)
    return out


def evaluate_target(df, score, target, algo, approach, max_false_alarm, extra=None):
    y=(df.model_key==target).to_numpy(int)
    score=np.asarray(score,dtype=float)
    if len(score)!=len(df) or not np.isfinite(score).all():
        raise ValueError('Invalid score size or nonfinite scores')
    threshold=threshold_for_false_alarm_limit(y,score,max_false_alarm)
    # A hard family gate can score true positives exactly zero. In that case
    # no strictly positive threshold may achieve the desired false-alarm cap.
    # Never use t=0: it would accept *every* out-of-family negative.
    if approach == 'hierarchy_hard_route' and threshold <= 0:
        threshold=np.nextafter(0.0,1.0)
    metrics=[]; pred=[]
    for rule,t in [('fixed_0.5',.5),('validation_false_alarm_limit',threshold)]:
        m=score_metrics(y,score,t,'validation',algo,target,rule)
        m.update({'approach':approach,'validation_prompts':df.prompt_id.nunique(),
                  'family':MODEL_TO_FAMILY[target]})
        if extra: m.update(extra)
        m['requested_max_false_alarm']=float(max_false_alarm)
        m['false_alarm_constraint_met']=bool(m['false_alarm_rate']<=max_false_alarm+1e-12)
        metrics.append(m)
        pred.append(make_pred(df,score,target,algo,approach,t,rule))
    return metrics,pred,threshold


def breakdowns(all_predictions):
    """Rates are conditional within subgroup; sample counts are always included."""
    rows=[]
    group_keys=[('prompt_category','prompt_category'),('persona_id','persona_id'),
                ('actual_model','model_key')]
    pivot=['approach','algorithm','target_model','threshold_rule']
    for key,chunk in all_predictions.groupby(pivot,dropna=False):
        for kind,col in group_keys:
            for value,part in chunk.groupby(col,dropna=False):
                y=part.label.to_numpy(int)
                p=part.predicted_target.to_numpy(int)
                scores=part.target_score.to_numpy(float)
                pos=int(y.sum()); neg=int((1-y).sum())
                tp=int(((y==1)&(p==1)).sum()); fn=pos-tp
                tn=int(((y==0)&(p==0)).sum()); fp=neg-tn
                rows.append(dict(zip(pivot,key)) | {
                    'group_by':kind,'group':value,'n':len(part),
                    'n_prompts':part.prompt_id.nunique(),
                    'positives':pos,'negatives':neg,
                    'tp':tp,'fn':fn,'tn':tn,'fp':fp,
                    'false_alarm_rate':fn/pos if pos else np.nan,
                    'change_detection_rate':tn/neg if neg else np.nan,
                    'false_acceptance_rate':fp/neg if neg else np.nan,
                    'roc_auc':roc_auc_score(y,scores) if pos and neg else np.nan,
                })
    return pd.DataFrame(rows)


def prompt_ranking(df, score, target, algo, approach):
    d=df[['prompt_id','prompt_category','model_key']].copy()
    d['label']=(d.model_key==target).astype(int)
    d['score']=np.asarray(score)
    g=d.groupby(['prompt_id','prompt_category','label']).score.mean().reset_index()
    p=g.pivot_table(index=['prompt_id','prompt_category'],columns='label',values='score')
    if 0 not in p or 1 not in p: return pd.DataFrame()
    p=p[[0,1]].dropna()
    out=p.reset_index().rename(columns={0:'negative_score_mean',1:'target_score_mean'})
    out['score_margin']=out['target_score_mean']-out['negative_score_mean']
    out['target_ranked_higher']=(out.score_margin>0).astype(int)
    out['target_model']=target;out['algorithm']=algo;out['approach']=approach
    return out
