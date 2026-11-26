"""Prepare, validate, register and configure a trusted classifier candidate."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fingerprinting.onboarding.artifacts import template, validate, register, candidate_config


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT,help='system directory (default: this script’s project)')
    sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('template');t.add_argument('--from-artifact',required=True);t.add_argument('--artifact-id',required=True);t.add_argument('--output',type=Path,required=True);t.add_argument('--dataset');t.add_argument('--split-id')
    v=sub.add_parser('validate');v.add_argument('bundle',type=Path)
    r=sub.add_parser('register');r.add_argument('bundle',type=Path);r.add_argument('--trust-bundle',action='store_true')
    c=sub.add_parser('candidate-config');c.add_argument('artifact_id');c.add_argument('--output',type=Path,required=True);c.add_argument('--base-config',type=Path);c.add_argument('--single',action='store_true');c.add_argument('--approach')
    a=p.parse_args(argv)
    try:
        if a.command=='template':
            template(a.root,a.from_artifact,a.artifact_id,a.output,dataset_id=a.dataset,split_id=a.split_id); result={'template':str(a.output),'status':'draft_complete_required_fields'}
        elif a.command=='validate':result=validate(a.root,a.bundle)
        elif a.command=='register':result=register(a.root,a.bundle,trust_bundle=a.trust_bundle)
        else: result=candidate_config(a.root,a.artifact_id,a.output,base=a.base_config,single=a.single,approach=a.approach)
        print(json.dumps(result,indent=2)); return 0
    except Exception as exc:
        print(f'Onboarding refused: {exc}',file=sys.stderr); return 2

if __name__=='__main__':sys.exit(main())
