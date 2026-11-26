"""Local training planning, execution and history; method adapters are reviewed code."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fingerprinting.training import orchestrator as o

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('plan','run'):
        s=sub.add_parser(name);s.add_argument('--config',type=Path,required=True);s.add_argument('--method',choices=o.METHODS)
        if name=='run':
            s.add_argument('--approve-dataset',action='store_true');s.add_argument('--register-candidates',action='store_true');s.add_argument('--evaluate-candidates',action='store_true');s.add_argument('--evaluation-base-config',type=Path,default=ROOT/'config/experiments/live_stage2_review.yaml');s.add_argument('--evaluation-prompts',type=Path)
    sub.add_parser('history');sub.add_parser('methods')
    args=p.parse_args(argv);root=args.root.resolve();trainers=o.available_trainers()
    try:
        if args.command=='history': result=o.history(root)
        elif args.command=='methods':result={m:('deferred' if m=='logistic_regression' else 'available' if m in trainers else 'trainer_not_integrated') for m in o.METHODS}
        elif args.command=='plan':result=o.plan(root,o.read_config(args.config),trainers,args.method)
        else:
            if args.evaluate_candidates and not args.register_candidates:raise ValueError('--evaluate-candidates requires --register-candidates')
            result=o.run(root,o.read_config(args.config),trainers,method=args.method,approve_dataset=args.approve_dataset,register_candidates=args.register_candidates)
            if args.evaluate_candidates and result['status'] in ('completed','partial'):
                from fingerprinting.release import evaluate_run
                result['release_evaluation']=evaluate_run(root,result['run_id'],args.evaluation_base_config,trust_artifacts=True,prompts=args.evaluation_prompts)
        print(json.dumps(result,indent=2,allow_nan=False));return 2 if args.command=='run' and (result['status']!='completed' or any(v['status']=='blocked' for v in result.get('release_evaluation',{}).get('methods',{}).values())) else 0
    except Exception as exc:
        print(f'Training refused: {exc}',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
