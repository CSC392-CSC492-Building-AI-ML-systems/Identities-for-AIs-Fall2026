#!/usr/bin/env python3
"""Apply a trained four-model family-first detector to ONE new response.

Example:
  python scripts/predict_hierarchical.py --target llama3.1-8b --algorithm baseline_lr --response-file new_response.txt

Do not load arbitrary third-party joblib model files (pickle deserialization risk).
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import joblib
import numpy as np
from train_hierarchical import compose_four_scores,score_positive
from experiment_common import FAMILIES,MODEL_TO_FAMILY


def predict(text,base,algo,target,approach):
    root=base/'models'/algo
    if target not in MODEL_TO_FAMILY:
        raise ValueError(f'Unknown target {target}; valid: {list(MODEL_TO_FAMILY)}')
    pg=score_positive(joblib.load(root/'family_gemini_vs_llama.joblib'),[text])[0]
    within={}
    for fam,(a,b) in FAMILIES.items():
        within[fam]=score_positive(joblib.load(root/f'{fam}_conditional_{a}.joblib'),[text])[0]
    scores={k:float(v[0]) for k,v in compose_four_scores(
        np.array([pg]),
        np.array([within['gemini']]),
        np.array([within['llama']])).items()}
    target_fam=MODEL_TO_FAMILY[target]
    route='gemini' if pg>=.5 else 'llama'
    cond=within[target_fam]
    if target in ('gemini-3.8-flash','llama3.2-3b'):cond=1-cond
    if approach=='hierarchy_soft':
        score=scores[target]
    elif approach=='hierarchy_hard_route':
        score=cond if route==target_fam else 0.0
    elif approach=='ovr_direct':
        score=float(score_positive(joblib.load(root/f'ovr_{target}.joblib'),[text])[0])
    else: raise ValueError(f'Bad approach: {approach}')
    cfg=json.loads((root/f'{approach}_{target}_threshold.json').read_text())
    threshold=float(cfg['validation_threshold'])
    return {'target_model':target,'algorithm':algo,'approach':approach,
            'candidate_model_metadata_used':False,
            'family_score_gemini':float(pg),
            'family_routed_to':route,
            'within_family_target_score':float(cond),
            'soft_scores_all_known_models':scores,
            'binary_target_score':float(score),'validation_threshold':threshold,
            'predicted_target':bool(score>=threshold),
            'interpretation':'consistent_with_target' if score>=threshold else 'possible_change',
            'note':'Experimental closed-set model scores; not calibrated probabilities or proof of identity.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results-root',type=Path,default=Path('collector/data/experiment5/hierarchy'))
    p.add_argument('--algorithm',default='baseline_lr')
    p.add_argument('--target',required=True,choices=list(MODEL_TO_FAMILY))
    p.add_argument('--approach',choices=['hierarchy_soft','hierarchy_hard_route','ovr_direct'],
                   default='hierarchy_soft')
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--response-file',type=Path)
    group.add_argument('--response-text')
    args=p.parse_args()
    txt=args.response_file.read_text(encoding='utf-8') if args.response_file else args.response_text
    if not txt.strip():p.error('Response must not be empty')
    print(json.dumps(predict(txt,args.results_root,args.algorithm,args.target,args.approach),indent=2))

if __name__=='__main__':main()
