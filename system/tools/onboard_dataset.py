"""Validate, register, split and export versioned collector datasets (offline)."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fingerprinting.onboarding import datasets
from fingerprinting.onboarding.artifacts import read_json


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT,help='System directory')
    sub=p.add_subparsers(dest='command',required=True)
    v=sub.add_parser('validate');v.add_argument('source',type=Path)
    r=sub.add_parser('register');r.add_argument('source',type=Path);r.add_argument('--version',required=True);r.add_argument('--source-note',required=True)
    a=sub.add_parser('audit');a.add_argument('dataset_id');a.add_argument('--reference',type=Path,action='append',required=True);a.add_argument('--split-id')
    s=sub.add_parser('split');s.add_argument('dataset_id');s.add_argument('--split-id',required=True);s.add_argument('--seed',type=int,default=42);s.add_argument('--weights',type=int,nargs=4,default=datasets.DEFAULT_WEIGHTS,metavar=('TRAIN','CAL','VAL','TEST'));s.add_argument('--prompt-aliases',type=Path);s.add_argument('--eligibility-policy',choices=datasets.ELIGIBILITY_POLICIES,default=datasets.CURRENT_ELIGIBILITY)
    f=sub.add_parser('split-panel');f.add_argument('dataset_id');f.add_argument('--split-id',required=True);f.add_argument('--prompt-set',required=True);f.add_argument('--probe-ids',nargs='+',required=True);f.add_argument('--personas',type=Path,required=True,help='JSON mapping of train/calibration/validation/test to persona IDs')
    i=sub.add_parser('inspect');i.add_argument('dataset_id');i.add_argument('--split-id')
    e=sub.add_parser('export');e.add_argument('dataset_id');e.add_argument('--split-id',required=True);e.add_argument('--partition',choices=datasets.PARTITIONS,required=True);e.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        if args.command=='validate':result=datasets.validate(args.root,args.source)
        elif args.command=='register':result=datasets.register(args.root,args.source,args.version,source_note=args.source_note)
        elif args.command=='audit':result=datasets.overlap(args.root,args.dataset_id,args.reference,split_id=args.split_id)
        elif args.command=='inspect':result=datasets.inspect_snapshot(args.root,args.dataset_id,args.split_id)
        elif args.command=='split-panel':result=datasets.split_fixed_panel(args.root,args.dataset_id,args.split_id,prompt_set=args.prompt_set,probe_ids=args.probe_ids,persona_partitions=read_json(args.personas))
        elif args.command=='split':result=datasets.split(args.root,args.dataset_id,args.split_id,seed=args.seed,weights=args.weights,aliases=read_json(args.prompt_aliases) if args.prompt_aliases else None,eligibility_policy=args.eligibility_policy)
        else:result=datasets.export(args.root,args.dataset_id,args.split_id,args.partition,args.output)
        print(json.dumps(result,indent=2,sort_keys=True));return 0
    except Exception as exc:
        # No record bodies are printed by validation; report only location/field errors.
        print(f'Dataset onboarding refused: {exc}',file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
