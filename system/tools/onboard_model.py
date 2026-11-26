"""Register canonical target models and prepare authoritative research cards (offline)."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fingerprinting.onboarding import identities as i

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('plan','register','draft-cards','publish-cards'):
        s=sub.add_parser(name);s.add_argument('submission',type=Path)
        if name in ('plan','register'):s.add_argument('--allow-new-family',action='store_true')
    sub.add_parser('status');a=p.parse_args(argv)
    try:
        if a.command=='status':r=i.status(a.root)
        else:
            s=i.spec_load(a.submission)
            if a.command=='plan':r=i.plan(a.root,s,a.allow_new_family)
            elif a.command=='register':r=i.register(a.root,s,a.allow_new_family)
            elif a.command=='draft-cards':r=i.draft(a.root,s)
            else:r=i.publish_cards(a.root,s)
        print(json.dumps(r,indent=2,ensure_ascii=False));return 0
    except Exception as e:print(f'Model onboarding refused: {e}',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
