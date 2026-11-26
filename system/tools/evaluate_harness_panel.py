"""Replay a frozen Harness panel through the existing Factory and evaluator.
Mock by default (plumbing only). Live judge requires explicit permission to
send probe/reference text to the configured judge, and an explicit case budget.
No target calls, no reference refresh, no policy activation.
"""
from __future__ import annotations
import argparse,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fingerprinting.onboarding import artifacts as a,datasets as d
from fingerprinting.training.random_forest import load_traces
from fingerprinting.adapters.builders import real_adapter_constructors
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import PipelineFactory
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.schemas import EvaluationCase,FingerprintRequest,Observation

def evaluate(root,config,output,*,partition='validation',max_cases=None,allow_live_judge=False):
    if partition not in ('validation','test'):raise ValueError('Choose validation or test')
    if max_cases is not None and (type(max_cases) is not int or not 1<=max_cases<=500):raise ValueError('Case limit must be 1–500')
    if allow_live_judge and max_cases is None:raise ValueError('Explicit --max-cases required for live judge')
    if output.exists():raise ValueError('Output already exists')
    reg=a.existing(root);cfg=load_pipeline_config(config,reg)
    if cfg.stage1.enabled or cfg.stage2.mode!='single' or cfg.stage2.methods[0].adapter!='harness':raise ValueError('Use Stage-1-off Harness-only configuration')
    m=reg.get(cfg.stage2.methods[0].artifact_id);p=m.provenance
    if m.options.get('reference_abi')!='catalog_reference_v2':raise ValueError('Use a v2 reference bundle')
    did,sid=p['training_dataset_id'],p['split_id'];info=d.inspect_snapshot(root,did,sid)
    if info['dataset_manifest_sha256']!=p['dataset_manifest_sha256'] or info['split_manifest_sha256']!=p['split_manifest_sha256']:raise ValueError('Dataset provenance mismatch')
    provider=m.options['judge_provider'] if allow_live_judge else 'mock'
    strategy=PipelineFactory(reg,real_adapter_constructors(harness_judge_provider=provider)).build_stage2(cfg)
    probes=strategy.identifiers[0].required_probes()
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'partition.jsonl';d.export(root,did,sid,partition,path)
        traces=load_traces(path,info['probe_pool'],info['prompt_set_version'])
    # Round-robin classes so a small smoke run covers several identities, not
    # just the alphabetically first class. This is a deterministic subset.
    by={k:[t for t in traces if t['model_id']==k] for k in sorted({t['model_id'] for t in traces})}
    ordered=[rs[i] for i in range(max(map(len,by.values()))) for rs in by.values() if i<len(rs)]
    selected=ordered[:max_cases] if max_cases is not None else ordered
    cases=[]
    for i,t in enumerate(selected):
        obs={q.probe_id:Observation(q.prompt_text,t['answers'][q.probe_id],q.probe_id,completed_blank=not t['answers'][q.probe_id].strip()) for q in probes}
        key=t['model_id'];case_id=f'harness-panel-{i:04d}'
        cases.append(EvaluationCase(case_id,FingerprintRequest(case_id,obs[probes[0].probe_id]),key,reg.catalog.get(key).family_id,did,sid,replay_probes=obs,persona_id=t['persona_id'],source_record_ids=[t['record_ids'][q.probe_id] for q in probes]))
    report=EvaluationRunner.stage2(cases,strategy); attempts=[r['attempts'][0] for r in report.rows]
    result={'artifact_id':m.artifact_id,'artifact_manifest_sha256':m.manifest_sha256,'dataset_id':did,'split_id':sid,'partition':partition,'split_manifest_sha256':info['split_manifest_sha256'],'judge_provider':provider,'judge_model':m.options['judge_model'],'stage1_enabled':False,'cases':len(cases),'available_cases':len(traces),'personas':sorted({t['persona_id'] for t in selected}),'errors':sum(x['outcome']=='error' for x in attempts),'accepted':sum(x['accepted_model'] is not None for x in attempts),'handoffs':sum(x['handoff_requested'] is True for x in attempts),'blank_probe_observations':sum(not t['answers'][q.probe_id].strip() for t in selected for q in probes),'target_api_calls':0,'independent_holdout_certified':False,'unknown_family_evaluated':False,'status':'mock_plumbing_only' if provider=='mock' else 'exploratory_live_judge_review_only'}
    if provider!='mock':
        # Do not persist judge reasons or probe text; those can echo private data.
        result['candidate_metrics']=report.metrics
        result['rows']=[{'case_id':r['case_id'],'actual_model':r['actual_model'],'candidate_model':x['candidate_model'],'score':x['score'],'outcome':x['outcome']} for r,x in zip(report.rows,attempts)]
    else:result['note']='Mock judge guesses randomly; identification accuracy intentionally omitted.'
    a.write_new(output,a.json_text(result));return result

def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--config',type=Path,required=True);cli.add_argument('--output',type=Path,required=True);cli.add_argument('--partition',choices=('validation','test'),default='validation');cli.add_argument('--max-cases',type=int);cli.add_argument('--allow-live-judge',action='store_true',help='Consent to send probe and reference text to the configured judge; potentially billable');args=cli.parse_args()
    try:
        r=evaluate(ROOT,args.config,args.output,partition=args.partition,max_cases=args.max_cases,allow_live_judge=args.allow_live_judge);print(a.json_text(r));return 2 if r['errors'] else 0
    except Exception as exc:print(f'Harness evaluation refused: {type(exc).__name__}: {exc}',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
