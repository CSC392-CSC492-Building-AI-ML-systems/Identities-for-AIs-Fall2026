"""Evaluate a frozen RF panel candidate on the fixed-probe test partition.

No query selection, no live calls, no automatic acceptance or promotion.
Optional comparison report reconstructs pre-selected prefix baselines from train only.
"""
from __future__ import annotations
import argparse,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fingerprinting.onboarding import artifacts as a,datasets as d
from fingerprinting.training.random_forest import load_traces,matrices,metrics
from fingerprinting.adapters import rf_panel_features as f
from fingerprinting.adapters.builders import real_adapter_constructors
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import PipelineFactory
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.schemas import EvaluationCase,FingerprintRequest,Observation


def evaluate(root,config_path,output,selection_report=None):
    reg=a.existing(root); cfg=load_pipeline_config(config_path,reg)
    if cfg.stage2.mode!='single' or cfg.stage2.methods[0].adapter!='random_forest':raise ValueError('Use RF-only candidate config')
    manifest=reg.get(cfg.stage2.methods[0].artifact_id); p=manifest.provenance;o=manifest.options
    if o.get('feature_abi')!=f.FEATURE_ABI:raise ValueError('Not an RF panel candidate')
    did,sid=p['training_dataset_id'],p['split_id'];info=d.inspect_snapshot(root,did,sid)
    if info['dataset_manifest_sha256']!=p['dataset_manifest_sha256'] or info['split_manifest_sha256']!=p['split_manifest_sha256'] or info['split_algorithm']!=d.PANEL_ALGORITHM:raise ValueError('Dataset provenance mismatch')
    strategy=PipelineFactory(reg,real_adapter_constructors()).build_stage2(cfg)
    panel=manifest.options['probe_ids'];spec=a.read_json(manifest.directory/'feature_manifest.json'); prompts={q['id']:q['text'] for q in spec['probes']}
    if output.exists():raise ValueError('Output already exists')
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp); d.export(root,did,sid,'test',tmp/'test.jsonl');test=load_traces(tmp/'test.jsonl',info['probe_pool'],info['prompt_set_version'])
        catalog=reg.catalog; cases=[]
        for i,t in enumerate(test):
            obs={pid:Observation(prompts[pid],t['answers'][pid],prompt_id=pid,completed_blank=not t['answers'][pid].strip()) for pid in panel}
            # Stage 2 ignores initial and expected identity; use first observed probe,
            # not an invented extra target query. No ground truth reaches identifier.
            key=t['model_id']; case_id=f'panel-{i:04d}'; req=FingerprintRequest(case_id,obs[panel[0]])
            cases.append(EvaluationCase(case_id,req,key,catalog.get(key).family_id,did,sid,replay_probes=obs,persona_id=t['persona_id'],source_record_ids=[t['record_ids'][pid] for pid in panel]))
        report=EvaluationRunner.stage2(cases,strategy);truth=[r['actual_model'] for r in report.rows];pred=[r['attempts'][0]['candidate_model'] for r in report.rows]
        if any(x is None for x in pred):raise ValueError('Candidate failed runtime evaluation')
        result={'artifact_id':manifest.artifact_id,'artifact_manifest_sha256':manifest.manifest_sha256,'dataset_id':did,'split_id':sid,'split_manifest_sha256':info['split_manifest_sha256'],'test_personas':sorted({t['persona_id'] for t in test}),'selected_panel':panel,'test_metrics':metrics(truth,pred,list(manifest.supported_models)), 'family_accuracy':sum(catalog.get(t).family_id==catalog.get(q).family_id for t,q in zip(truth,pred))/len(truth),'pipeline_metrics':report.metrics,'blank_test_probe_count':sum(not t['answers'][pid].strip() for t in test for pid in panel),'independent_holdout_certified':False,'unknown_family_evaluated':False,'note':'Fixed known prompts; unseen persona IDs only. Reconstructed independent library queries, not actual multi-turn sessions.'}
        if selection_report:
            # Compare ONLY the fixed prefixes already chosen using validation;
            # the evaluation labels never determine the order or budget.
            from sklearn.ensemble import RandomForestClassifier
            sel=a.read_json(selection_report);order=sel['selected_panel']; rounds=sel['rounds']
            if set(order)!=set(info['probe_pool']) or len(order)!=len(info['probe_pool']) or order[:len(panel)]!=panel or sel.get('test_used') is not False:raise ValueError('Selection report does not match frozen panel')
            if [r['selected'] for r in rounds]!=[order[:i] for i in range(1,len(order)+1)]:raise ValueError('Invalid prefix sequence')
            d.export(root,did,sid,'train',tmp/'train.jsonl');train=load_traces(tmp/'train.jsonl',info['probe_pool'],info['prompt_set_version']);x=matrices(train,order);v=matrices(test,order);y=[t['model_id'] for t in train];vy=[t['model_id'] for t in test];comparison=[]
            for i,pid in enumerate(order,1):
                cols=f.columns(order[:i]);model=RandomForestClassifier(n_estimators=o['n_estimators'],random_state=o['random_state'],class_weight='balanced',min_samples_leaf=o['min_samples_leaf'],max_depth=o['max_depth'],n_jobs=1);model.fit(x[cols],y);preds=model.predict(v[cols]);m=metrics(vy,preds,list(manifest.supported_models))
                if i==len(panel) and list(preds)!=pred:raise ValueError('Frozen prefix refit differs from registered model')
                comparison.append({'budget':i,'added_probe':pid,'selected':i==len(panel),'validation_accuracy':rounds[i-1]['validation']['accuracy'],'test_accuracy':m['accuracy'],'test_macro_f1':m['macro_f1'],'correct':sum(t==q for t,q in zip(vy,preds)),'test_traces':len(vy)})
            result['frozen_prefix_comparison']=comparison
    output.parent.mkdir(parents=True,exist_ok=True);a.write_new(output,a.json_text(result));return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--config',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--selection-report',type=Path);args=parser.parse_args()
    try:
        result=evaluate(args.root,args.config,args.output,args.selection_report);print(json.dumps({'test_accuracy':result['test_metrics']['accuracy'],'test_traces':result['test_metrics']['traces'],'accepted':result['pipeline_metrics']['accepted'],'comparison':result.get('frozen_prefix_comparison')},indent=2));return 0
    except Exception as exc:print(f'Panel evaluation refused: {exc}',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
