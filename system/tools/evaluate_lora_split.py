"""Evaluate a frozen notebook-derived LoRA artifact on its pinned test split.

No training, threshold selection, or activation. Requires real inference deps.
"""
import argparse,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fingerprinting.onboarding import artifacts as a,datasets as d
from fingerprinting.training.lora import load_rows,_balance,metrics
from fingerprinting.adapters.lora_preprocessing import BLANK_POLICY
from fingerprinting.adapters.builders import real_adapter_constructors
from fingerprinting.factory import PipelineFactory
from fingerprinting.config import load_pipeline_config
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.schemas import EvaluationCase,FingerprintRequest,Observation


def evaluate(root,config_path,output):
    if output.exists():raise ValueError('Output already exists')
    reg=a.existing(root);cfg=load_pipeline_config(config_path,reg)
    if cfg.stage2.mode!='single' or cfg.stage2.methods[0].adapter!='lora':raise ValueError('Use a LoRA-only candidate config')
    m=reg.get(cfg.stage2.methods[0].artifact_id);p=m.provenance;o=m.options
    if o.get('input_policy')!=BLANK_POLICY or o.get('label_order_status')!='confirmed' or o.get('acceptance_policy')!={'mode':'review_only'}:raise ValueError('Expected a new review-only LoRA training artifact')
    did,sid=p['training_dataset_id'],p['split_id'];info=d.inspect_snapshot(root,did,sid)
    if info['dataset_manifest_sha256']!=p['dataset_manifest_sha256'] or info['split_manifest_sha256']!=p['split_manifest_sha256']:raise ValueError('Dataset provenance mismatch')
    labels=list(o['label_order']);strategy=PipelineFactory(reg,real_adapter_constructors()).build_stage2(cfg)
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'test.jsonl';d.export(root,did,sid,'test',path)
        rows=load_rows(path);selected,balance=_balance(rows,labels,p['training_parameters']['seed'],None)
    # For a fixed panel the test shared prompts must match training's frozen panel.
    if info['split_algorithm']==d.PANEL_ALGORITHM:
        if balance['shared_prompts']!=a.read_json(m.directory/'data_report.json')['train']['shared_prompts']:raise ValueError('Held-out fixed panel does not match training panel')
    cases=[]
    for i,r in enumerate(selected):
        cid=f'lora-test-{i:06d}';key=r['model'];raw=r['raw_text']
        # Original prompt text is absent from collector rows. This identifier only
        # reads response text; the prompt ID is an explicit replay placeholder.
        obs=Observation('Replay prompt ID: '+r['prompt'][1],raw,prompt_id=r['prompt'][1],completed_blank=r['blank'])
        cases.append(EvaluationCase(cid,FingerprintRequest(cid,obs),key,reg.catalog.get(key).family_id,did,sid,persona_id=r['persona'],source_record_ids=[r['id']]))
    report=EvaluationRunner.stage2(cases,strategy);truth=[r['actual_model'] for r in report.rows];pred=[r['attempts'][0]['candidate_model'] for r in report.rows]
    if any(x is None for x in pred):raise ValueError('Real candidate inference failed; inspect dependencies and checkpoint')
    result={'artifact_id':m.artifact_id,'artifact_manifest_sha256':m.manifest_sha256,'dataset_id':did,'split_id':sid,'split_manifest_sha256':info['split_manifest_sha256'],'test_data':balance,'test_metrics':metrics(truth,pred,labels),'family_accuracy':sum(reg.catalog.get(t).family_id==reg.catalog.get(q).family_id for t,q in zip(truth,pred))/len(truth),'pipeline_metrics':report.metrics,'independent_holdout_certified':False,'unknown_family_evaluated':False,'test_unit':'single response, not a multi-query trace','test_personas':sorted({r['persona'] for r in selected if r['persona'] is not None})}
    a.write_new(output,a.json_text(result));return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    try: result=evaluate(ROOT,args.config,args.output);print(a.json_text(result['test_metrics']));return 0
    except Exception as exc:print(f'LoRA evaluation refused: {exc}',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
