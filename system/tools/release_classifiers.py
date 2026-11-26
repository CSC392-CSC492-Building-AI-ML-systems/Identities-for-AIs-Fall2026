"""Evaluate and explicitly publish immutable local Stage 2 review profiles."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fingerprinting import release as r
from fingerprinting.onboarding.artifacts import json_text

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    e=sub.add_parser('evaluate');e.add_argument('--candidate',required=True);e.add_argument('--baseline');e.add_argument('--output',type=Path,required=True);e.add_argument('--partition',choices=('validation','test'),default='validation');e.add_argument('--initial-probe',default='I1');e.add_argument('--prompts',type=Path);e.add_argument('--max-cases',type=int);e.add_argument('--allow-live-judge',action='store_true');e.add_argument('--trust-artifacts',action='store_true')
    s=sub.add_parser('publish');s.add_argument('--evidence',type=Path,required=True);s.add_argument('--base-config',type=Path,default=ROOT/'config/experiments/live_stage2_review.yaml');s.add_argument('--release-id',required=True);s.add_argument('--review-note',required=True);s.add_argument('--acknowledge-exploratory',action='store_true');s.add_argument('--acknowledge-regression',action='store_true')
    b=sub.add_parser('rollback');b.add_argument('--source-release',required=True);b.add_argument('--release-id',required=True);b.add_argument('--review-note',required=True)
    t=sub.add_parser('evaluate-run');t.add_argument('--run-id',required=True);t.add_argument('--base-config',type=Path,default=ROOT/'config/experiments/live_stage2_review.yaml');t.add_argument('--output-dir',type=Path);t.add_argument('--prompts',type=Path);t.add_argument('--trust-artifacts',action='store_true')
    sub.add_parser('history');args=p.parse_args()
    try:
        if args.action=='evaluate':
            result=r.evaluate(ROOT,args.candidate,args.output,baseline=args.baseline,partition=args.partition,initial_probe=args.initial_probe,prompts=args.prompts,max_cases=args.max_cases,allow_live_judge=args.allow_live_judge,trust_artifacts=args.trust_artifacts)
            result={k:v for k,v in result.items() if k not in ('candidate','baseline') } | {'candidate':{k:v for k,v in result['candidate'].items() if k!='rows'},'baseline':{k:v for k,v in result['baseline'].items() if k!='rows'} if result['baseline'] else None}
        elif args.action=='evaluate-run':result=r.evaluate_run(ROOT,args.run_id,args.base_config,trust_artifacts=args.trust_artifacts,output_dir=args.output_dir,prompts=args.prompts)
        elif args.action=='publish':result=r.publish(ROOT,args.evidence,args.base_config,args.release_id,review_note=args.review_note,acknowledge_exploratory=args.acknowledge_exploratory,acknowledge_regression=args.acknowledge_regression)
        elif args.action=='rollback':result=r.rollback(ROOT,args.source_release,args.release_id,review_note=args.review_note)
        else:result=r.history(ROOT)
        print(json_text(result));return 2 if args.action=='evaluate-run' and any(v['status']=='blocked' for v in result['methods'].values()) else 0
    except Exception as exc:
        print(f'Release operation refused: {type(exc).__name__}: {exc}',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
