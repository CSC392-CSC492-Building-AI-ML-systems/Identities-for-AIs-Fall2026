#!/usr/bin/env python3
"""Experiment 6: four-model family-first fingerprinting vs direct one-vs-rest.

One family detector: Gemini (1) vs Llama (0). Within each family one pair
classifier. A target's soft score = family score * within-family score.
Also evaluates a hard family routing variant, and re-trained OVR baselines.
All fits use development only; all threshold tuning and reporting use validation.
"""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score,confusion_matrix,roc_auc_score
from train_rich_features import make_model
from experiment_common import FAMILIES,MODEL_TO_FAMILY,load_data,make_pred,evaluate_target,breakdowns

METHODS=['baseline_rf','baseline_lr','rich_rf','hybrid_lr','char_lr']

def score_positive(estimator, X):
    p=estimator.predict_proba(X)
    return p[:,list(estimator.classes_).index(1)]


def compose_four_scores(p_gemini,p_gemini_pro,p_llama31):
    """Soft pair of decisions, normalized to sum to one across known 4 models."""
    return {
        'gemini-3.1-pro':p_gemini*p_gemini_pro,
        'gemini-3.8-flash':p_gemini*(1-p_gemini_pro),
        'llama3.1-8b':(1-p_gemini)*p_llama31,
        'llama3.2-3b':(1-p_gemini)*(1-p_llama31),
    }


def run(args):
    dev,val=load_data(args.data_root,args.view)
    Xd=dev.response_text.astype(str).tolist()
    Xv=val.response_text.astype(str).tolist()
    out=args.out
    comp=out/'comparison'
    comp.mkdir(parents=True,exist_ok=True)
    metrics=[]; predictions=[]; family_metrics=[]; routed=[]
    for alg in dict.fromkeys(args.models):
        print(f'Hierarchy algorithm: {alg}',flush=True)
        fam_clf=make_model(alg,args.seed,args.embedding_model)
        yf=(dev.model_key.map(MODEL_TO_FAMILY)=='gemini').to_numpy(int)
        yfv=(val.model_key.map(MODEL_TO_FAMILY)=='gemini').to_numpy(int)
        fam_clf.fit(Xd,yf)
        pg=score_positive(fam_clf,Xv)
        family_metrics.append({
            'algorithm':alg,'n':len(val),'n_prompts':val.prompt_id.nunique(),
            'accuracy_0.5':accuracy_score(yfv,pg>=.5),
            'roc_auc':roc_auc_score(yfv,pg),
            'gemini_rows':int(yfv.sum()),'llama_rows':int((1-yfv).sum()),
        })
        artefacts=out/'models'/alg;artefacts.mkdir(parents=True,exist_ok=True)
        joblib.dump(fam_clf,artefacts/'family_gemini_vs_llama.joblib',compress=3)
        within={}
        for fam,(a,b) in FAMILIES.items():
            d=dev[dev.model_key.isin((a,b))]
            y=(d.model_key==a).to_numpy(int)
            pair_model=make_model(alg,args.seed,args.embedding_model)
            pair_model.fit(d.response_text.astype(str).tolist(),y)
            # Evaluate on ALL validation responses, even outside this family.
            # Conditional scores outside the family have no standalone meaning;
            # the family gate is responsible for downweighting those scores.
            within[fam]=score_positive(pair_model,Xv)
            joblib.dump(pair_model,artefacts/f'{fam}_conditional_{a}.joblib',compress=3)
        soft=compose_four_scores(pg,within['gemini'],within['llama'])
        if not np.allclose(sum(soft.values()),np.ones(len(val)),atol=1e-10):
            raise AssertionError('Hierarchical scores must sum to one across four known models')
        hard_family=np.where(pg>=.5,'gemini','llama')
        hard_model=np.where(pg>=.5,
                            np.where(within['gemini']>=.5,'gemini-3.1-pro','gemini-3.8-flash'),
                            np.where(within['llama']>=.5,'llama3.1-8b','llama3.2-3b'))
        max_score_model=np.array(list(soft))[np.argmax(np.column_stack(list(soft.values())),axis=1)]
        routed.append(pd.DataFrame({
            'record_id':val.record_id,'prompt_id':val.prompt_id,
            'actual_model':val.model_key,
            'actual_family':val.model_key.map(MODEL_TO_FAMILY),
            'family_score_gemini':pg,'predicted_family_0_5':hard_family,
            'predicted_model_hard':hard_model,'predicted_model_soft_argmax':max_score_model,
            'algorithm':alg,'correct_family':hard_family==val.model_key.map(MODEL_TO_FAMILY),
            'correct_model_hard':hard_model==val.model_key,
            'correct_model_soft_argmax':max_score_model==val.model_key,
        }))
        for target in MODEL_TO_FAMILY:
            target_family=MODEL_TO_FAMILY[target]
            p_fam = pg if target_family=='gemini' else 1-pg
            conditional=within[target_family]
            if target=='gemini-3.8-flash' or target=='llama3.2-3b':
                conditional=1-conditional
            hard=p_fam*0 + np.where(hard_family==target_family,conditional,0.)
            direct_clf=make_model(alg,args.seed,args.embedding_model)
            direct_clf.fit(Xd,(dev.model_key==target).to_numpy(int))
            direct=score_positive(direct_clf,Xv)
            joblib.dump(direct_clf,artefacts/f'ovr_{target}.joblib',compress=3)
            for approach,sc in [('ovr_direct',direct),('hierarchy_soft',soft[target]),
                                ('hierarchy_hard_route',hard)]:
                m, pred, t=evaluate_target(val,sc,target,alg,approach,args.max_false_alarm)
                for z in m: z['model_pair']=FAMILIES[target_family]
                metrics.extend(m)
                predictions.extend(pred)
                (artefacts/f'{approach}_{target}_threshold.json').write_text(json.dumps({
                    'target':target,'algorithm':alg,'approach':approach,
                    'validation_threshold':t,'max_false_alarm':args.max_false_alarm,
                },indent=2)+'\n')
    metrics_df=pd.DataFrame(metrics)
    pred_df=pd.concat(predictions,ignore_index=True)
    route_df=pd.concat(routed,ignore_index=True)
    metrics_df.to_csv(comp/'hierarchy_vs_ovr_metrics.csv',index=False)
    compare = metrics_df.pivot_table(
        index=['target_model','algorithm','threshold_rule'], columns='approach',
        values=['roc_auc','balanced_accuracy','false_alarm_rate','change_detection_rate'],
        aggfunc='first')
    deltas=[]
    for (target,alg,rule),row in compare.iterrows():
        for variant in ['hierarchy_soft','hierarchy_hard_route']:
            if ('roc_auc',variant) not in compare.columns: continue
            entry={'target_model':target,'algorithm':alg,'threshold_rule':rule,
                   'hierarchy_variant':variant}
            for measure in ['roc_auc','balanced_accuracy','false_alarm_rate','change_detection_rate']:
                entry['ovr_'+measure]=row[(measure,'ovr_direct')]
                entry['hierarchy_'+measure]=row[(measure,variant)]
                entry['delta_'+measure]=row[(measure,variant)]-row[(measure,'ovr_direct')]
            deltas.append(entry)
    pd.DataFrame(deltas).to_csv(comp/'hierarchy_improvement_deltas.csv',index=False)
    pred_df.to_csv(comp/'hierarchy_vs_ovr_predictions.csv',index=False)
    breakdowns(pred_df).to_csv(comp/'hierarchy_negative_model_category_rates.csv',index=False)
    pd.DataFrame(family_metrics).to_csv(comp/'family_stage_metrics.csv',index=False)
    route_df.to_csv(comp/'hierarchy_routing_predictions.csv',index=False)
    route_df.groupby('algorithm').agg(
        n=('actual_model','size'),
        family_accuracy=('correct_family','mean'),
        model_accuracy_hard=('correct_model_hard','mean'),
        model_accuracy_soft_argmax=('correct_model_soft_argmax','mean')
    ).reset_index().to_csv(comp/'hierarchy_routing_metrics.csv',index=False)
    (comp/'manifest.json').write_text(json.dumps({
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'data_root':str(args.data_root),'view':args.view,'models':args.models,
        'seed':args.seed,'max_false_alarm':args.max_false_alarm,
        'train_split':'development','validation_split':'validation',
        'test_read':False,
        'purpose':'known-four-model family->within-family gating for single-target Boolean change detection',
        'score_warning':'Class-weighted model outputs are uncalibrated; soft products are heuristic scores, not verified probabilities.',
        'unknown_family_warning':'The family stage is closed-set Gemini vs Llama. A never-seen family is forced into one of these and cannot be reliably identified as unknown.',
    },indent=2)+'\n')
    print('Saved comparisons:',comp.resolve())
    print('No test data accessed.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,default=Path('system/.local/stage1/supervised'))
    p.add_argument('--out',type=Path,default=Path('system/.local/stage1/experiment5/hierarchy'))
    p.add_argument('--view',default='all_personas')
    p.add_argument('--models',nargs='+',choices=METHODS,default=['baseline_rf','baseline_lr'])
    p.add_argument('--embedding-model',default='sentence-transformers/all-MiniLM-L6-v2')
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--max-false-alarm',type=float,default=.10)
    args=p.parse_args()
    if not 0<=args.max_false_alarm<1:p.error('--max-false-alarm must be in [0,1)')
    run(args)

if __name__=='__main__':main()
