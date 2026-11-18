#!/usr/bin/env python3
"""Experiment 5A + 5B: richer response-only within-family features and category diagnostics.

No test data is read. Train on development, evaluate on validation.
Feature sets can be run independently, including group ablations and optional embeddings.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from datetime import datetime,timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import FeatureUnion,Pipeline

from train_baselines import make_random_forest, make_tfidf_lr
from rich_features import RichStylometryTransformer, ALL_NAMES
from experiment_common import FAMILIES,load_data,breakdowns,evaluate_target,prompt_ranking

DEFAULT_SETS=['baseline_rf','baseline_lr','rich_rf','word_lr','char_lr','hybrid_lr']
AVAILABLE=DEFAULT_SETS+['rich_lr','embedding_lr']+[f'rich_rf_no_{g}' for g in ('lexical','formatting','code','syntax')]


def lr(seed):
    return LogisticRegression(C=1.0,class_weight='balanced',solver='liblinear',
                              max_iter=1500,random_state=seed)

def make_model(choice,seed,embedding_model):
    if choice=='baseline_rf': return make_random_forest(seed)
    if choice=='baseline_lr': return make_tfidf_lr(seed)
    if choice.startswith('rich_rf'):
        groups=(choice[len('rich_rf_no_'):],) if choice.startswith('rich_rf_no_') else ()
        return Pipeline([('rich',RichStylometryTransformer(drop_groups=groups)),
                         ('imputer',SimpleImputer(strategy='median')),
                         ('classifier',RandomForestClassifier(
                             n_estimators=300,min_samples_leaf=2,max_features='sqrt',
                             class_weight='balanced_subsample',random_state=seed,n_jobs=-1))])
    if choice=='rich_lr':
        return Pipeline([('rich',RichStylometryTransformer()),
                         ('imputer',SimpleImputer(strategy='median')),
                         ('scale',StandardScaler()),('classifier',lr(seed))])
    if choice=='embedding_lr':
        from embeddings import SentenceEmbeddingTransformer
        return Pipeline([('embedding',SentenceEmbeddingTransformer(model_name=embedding_model)),
                         ('scale',StandardScaler()),('classifier',lr(seed))])
    if choice in ('word_lr','char_lr','hybrid_lr'):
        branches=[]
        if choice in ('word_lr','hybrid_lr'):
            branches.append(('word',TfidfVectorizer(analyzer='word',ngram_range=(1,2),
                             min_df=2,max_features=35000,strip_accents='unicode',sublinear_tf=True)))
        if choice in ('char_lr','hybrid_lr'):
            branches.append(('char',TfidfVectorizer(analyzer='char',ngram_range=(3,5),
                             min_df=2,max_features=65000,strip_accents='unicode',sublinear_tf=True)))
        if choice=='hybrid_lr':
            branches.append(('rich',Pipeline([('features',RichStylometryTransformer()),
                           ('imputer',SimpleImputer(strategy='median')),
                           ('scale',StandardScaler(with_mean=False))])))
        return Pipeline([('features',FeatureUnion(branches)),('classifier',lr(seed))])
    raise ValueError(f'Unknown feature set: {choice}')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,default=Path('collector/data/supervised'))
    p.add_argument('--out',type=Path,default=Path('collector/data/experiment5/features'))
    p.add_argument('--view',default='all_personas')
    p.add_argument('--families',nargs='+',choices=list(FAMILIES),default=list(FAMILIES))
    p.add_argument('--feature-sets',nargs='+',choices=AVAILABLE,default=DEFAULT_SETS)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--max-false-alarm',type=float,default=.10)
    p.add_argument('--embedding-model',default='sentence-transformers/all-MiniLM-L6-v2')
    args=p.parse_args()
    if not 0<=args.max_false_alarm<1: p.error('max-false-alarm must be in [0,1)')
    dev,val=load_data(args.data_root,args.view)
    metrics=[];preds=[];prompts=[]
    args.out.mkdir(parents=True,exist_ok=True)
    for fam in dict.fromkeys(args.families):
        a,b=FAMILIES[fam]
        d=dev[dev.model_key.isin((a,b))].copy()
        v=val[val.model_key.isin((a,b))].copy()
        X_dev=d.response_text.astype(str).tolist()
        X_val=v.response_text.astype(str).tolist()
        if not set((a,b)).issubset(set(d.model_key)):
            raise ValueError('Insufficient classes in development: '+fam)
        for target in (a,b):
            y=(d.model_key==target).to_numpy(int)
            for choice in dict.fromkeys(args.feature_sets):
                print(f'Feature experiment: {fam}, target={target}, method={choice}',flush=True)
                model=make_model(choice,args.seed,args.embedding_model)
                model.fit(X_dev,y)
                scores=model.predict_proba(X_val)[:,list(model.classes_).index(1)]
                extra={'feature_set':choice,'sibling_model':b if target==a else a,
                       'development_responses':len(d)}
                m,pred,threshold=evaluate_target(v,scores,target,choice,'within_family',
                                                   args.max_false_alarm,extra)
                metrics.extend(m)
                for x in pred:
                    x['feature_set']=choice
                    preds.append(x)
                pr=prompt_ranking(v,scores,target,choice,'within_family')
                if not pr.empty:
                    pr['feature_set']=choice
                    prompts.append(pr)
                output=args.out/fam/target
                output.mkdir(parents=True,exist_ok=True)
                joblib.dump(model,output/f'{choice}.joblib',compress=3)
                (output/f'{choice}_threshold.json').write_text(json.dumps(
                    {'threshold':threshold,'target_model':target,'feature_set':choice,
                     'max_false_alarm':args.max_false_alarm,'selection_split':'validation'},indent=2)+'\n')
                if choice.startswith('rich_rf'):
                    names=model.named_steps['rich'].get_feature_names_out()
                    importance=model.named_steps['classifier'].feature_importances_
                    pd.DataFrame({'feature':names,'importance':importance}).sort_values(
                        'importance',ascending=False).to_csv(output/f'{choice}_feature_importance.csv',index=False)
    pred=pd.concat(preds,ignore_index=True)
    comp=args.out/'comparison';comp.mkdir(parents=True,exist_ok=True)
    metrics_df=pd.DataFrame(metrics)
    metrics_df.to_csv(comp/'feature_validation_metrics.csv',index=False)
    # Exploratory feature-set deltas relative to the corresponding earlier baseline.
    comparisons=[]
    for _,m in metrics_df.iterrows():
        baseline='baseline_rf' if m.algorithm.startswith('rich_rf') else 'baseline_lr'
        if m.algorithm in ('baseline_rf','baseline_lr'):continue
        matching=metrics_df[(metrics_df.target_model==m.target_model) &
                            (metrics_df.threshold_rule==m.threshold_rule) &
                            (metrics_df.algorithm==baseline)]
        if matching.empty:continue
        b=matching.iloc[0]
        comparisons.append({
            'target_model':m.target_model,'feature_set':m.algorithm,
            'baseline':baseline,'threshold_rule':m.threshold_rule,
            'auc_delta':m.roc_auc-b.roc_auc,
            'balanced_accuracy_delta':m.balanced_accuracy-b.balanced_accuracy,
            'false_alarm_delta':m.false_alarm_rate-b.false_alarm_rate,
            'change_detection_delta':m.change_detection_rate-b.change_detection_rate,
        })
    if comparisons:
        pd.DataFrame(comparisons).to_csv(comp/'feature_vs_baseline_deltas.csv',index=False)
    pred.to_csv(comp/'feature_validation_predictions.csv',index=False)
    breakdowns(pred).to_csv(comp/'feature_category_and_model_rates.csv',index=False)
    if prompts:
        ps=pd.concat(prompts,ignore_index=True)
        ps.to_csv(comp/'feature_prompt_scores.csv',index=False)
        s=ps.groupby(['target_model','algorithm','prompt_category']).agg(
            prompts=('prompt_id','nunique'),wins=('target_ranked_higher','sum'),
            mean_margin=('score_margin','mean')).reset_index()
        s['win_rate']=s.wins/s.prompts
        s.to_csv(comp/'feature_prompt_category_summary.csv',index=False)
    (comp/'manifest.json').write_text(json.dumps({
        'created_utc':datetime.now(timezone.utc).isoformat(),'source':str(args.data_root),
        'view':args.view,'families':args.families,'feature_sets':args.feature_sets,
        'seed':args.seed,'max_false_alarm':args.max_false_alarm,
        'embeddings_model':args.embedding_model if 'embedding_lr' in args.feature_sets else None,
        'train':'development','evaluate':'validation','final_test_accessed':False,
        'warning':'Category and persona metrics may use very few prompts. Feature selection on validation may overfit.'
    },indent=2)+'\n')
    print('Finished. Reports:',comp.resolve())
    print('No test data accessed.')

if __name__=='__main__': main()
