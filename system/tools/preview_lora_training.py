"""Inspect balanced LoRA data without downloading weights or running training."""
import argparse,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fingerprinting.training.lora import parameters,prepare_data
from fingerprinting.onboarding import artifacts as a,datasets as d

def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--config',type=Path,required=True);cli.add_argument('--output',type=Path);args=cli.parse_args()
    cfg=a.read_json(args.config);p=parameters(cfg['methods']['lora']['parameters'],require_revision=False)
    info=d.inspect_snapshot(ROOT,cfg['dataset_id'],cfg['split_id'])
    with tempfile.TemporaryDirectory() as tmp:
        paths={k:Path(tmp)/(k+'.jsonl') for k in ('train','validation')}
        for k,path in paths.items():d.export(ROOT,cfg['dataset_id'],cfg['split_id'],k,path)
        _,_,_,report=prepare_data(paths['train'],paths['validation'],p,info['split_algorithm'])
    report.update(dataset_id=cfg['dataset_id'],split_id=cfg['split_id'],dataset_manifest_sha256=info['dataset_manifest_sha256'],split_manifest_sha256=info['split_manifest_sha256'],weights_loaded=False)
    if args.output:a.write_new(args.output,a.json_text(report))
    print(a.json_text(report));return 0
if __name__=='__main__':sys.exit(main())
