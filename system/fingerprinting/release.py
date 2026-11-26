"""Local, review-only artifact release workflow. No automatic activation or judge consent.

The local operator is trusted; report hashes detect changes, not forged evidence.
Only the fixed-panel protocol is currently supported by this comparison runner.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile

from .onboarding import artifacts as a, datasets as d
from .config import load_pipeline_config
from .factory import PipelineFactory
from .adapters.builders import real_adapter_constructors
from .evaluation import EvaluationRunner
from .schemas import EvaluationCase, FingerprintRequest, Observation
from .training.random_forest import load_traces

SCHEMA = 'stage2_release_evidence_v1'
MISSING = '__no_prediction__'
ORDER = ('lora', 'harness', 'random_forest')


def need(ok, msg):
    if not ok:
        raise ValueError(msg)


def now():
    return datetime.now(timezone.utc).isoformat()


def stable_hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def evidence_environment(root):
    import importlib.metadata as md
    deps = {}
    for name in ('scikit-learn', 'pandas', 'numpy', 'joblib', 'torch', 'transformers', 'peft', 'PyYAML', 'google-genai', 'openai'):
        try:
            deps[name] = md.version(name)
        except md.PackageNotFoundError:
            deps[name] = None
    files = {p.relative_to(root).as_posix(): a.digest(p) for p in sorted((root/'fingerprinting').rglob('*.py'))}
    return {'source_sha256': stable_hash(files), 'catalog_sha256': a.digest(root/'catalog/models.json'), 'dependencies': deps}


def artifact_info(reg, aid):
    m = reg.get(aid)
    need(m.stage == 2 and m.adapter in ORDER, 'Stage 1 is deferred')
    need(reg.readiness(aid).ready, f'Artifact not ready: {aid}')
    return m


def check_review_only(m):
    o = m.options
    if m.adapter == 'harness':
        need(o.get('reference_abi') == 'catalog_reference_v2' and o.get('acceptance_policy') == 'review_only', 'Expected review-only catalog Harness')
    else:
        need(o.get('acceptance_policy') == {'mode': 'review_only'}, 'Expected review-only classifier')
    if m.adapter == 'lora':
        need(o.get('label_order_status') == 'confirmed' and re.fullmatch('[0-9a-fA-F]{40}', str(o.get('base_model_revision', ''))), 'LoRA label mapping or base revision unverified')


def check_lora(m):
    if m.adapter == 'lora':
        need(m.options.get('label_order_status') == 'confirmed' and re.fullmatch('[0-9a-fA-F]{40}', str(m.options.get('base_model_revision', ''))), 'LoRA label mapping or base revision unverified; do not score this checkpoint')


def summarize(rows, catalog):
    from sklearn.metrics import f1_score, confusion_matrix
    need(bool(rows), 'Empty evaluation cohort')
    y = [r['actual_model'] for r in rows]
    p = [r['candidate_model'] or MISSING for r in rows]
    labels = sorted(set(y))
    axes = sorted(set(y) | set(p))
    n = len(y)
    correct = sum(t == q for t, q in zip(y, p))
    predicted = sum(q != MISSING for q in p)
    fam_correct = sum(q != MISSING and catalog.get(t).family_id == catalog.get(q).family_id for t, q in zip(y, p))
    return {'cases': n, 'correct': correct, 'accuracy': correct/n,
            'macro_f1': float(f1_score(y, p, labels=labels, average='macro', zero_division=0)),
            'family_accuracy': fam_correct/n, 'candidate_coverage': predicted/n,
            'missing_predictions': n-predicted, 'errors': sum(r['outcome'] == 'error' for r in rows),
            'accepted': sum(r['accepted_model'] is not None for r in rows),
            'class_counts': dict(Counter(y)), 'confusion_labels': axes,
            'confusion_matrix': confusion_matrix(y, p, labels=axes).tolist(),
            'per_model': {k: {'cases': y.count(k), 'correct': sum(t==q==k for t,q in zip(y,p))} for k in labels},
            'mean_additional_replay_probes': sum(r['additional_probes'] for r in rows)/n,
            'mean_identifier_ms': sum(r['duration_ms'] or 0 for r in rows)/n}


def _strategy(root, reg, m, judge):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td)/'single.yaml'
        a.candidate_config(root, m.artifact_id, path, single=True)
        cfg = load_pipeline_config(path, reg)
        return PipelineFactory(reg, real_adapter_constructors(harness_judge_provider=judge)).build_stage2(cfg)


def _paired_metrics(candidate, baseline, common, catalog):
    c = [r for r in candidate if r['actual_model'] in common]
    b = [r for r in baseline if r['actual_model'] in common]
    if not c:
        return None
    need([(r['case_id'], r['actual_model']) for r in c] == [(r['case_id'], r['actual_model']) for r in b], 'Paired cohort mismatch')
    cm,bm = summarize(c,catalog),summarize(b,catalog)
    return {'shared_labels': sorted(common), 'candidate':cm, 'baseline':bm,
            'delta':{k:cm[k]-bm[k] for k in ('accuracy','macro_f1','family_accuracy','candidate_coverage')},
            'candidate_only_correct':sum(x['actual_model']==x['candidate_model'] and y['actual_model']!=y['candidate_model'] for x,y in zip(c,b)),
            'baseline_only_correct':sum(y['actual_model']==y['candidate_model'] and x['actual_model']!=x['candidate_model'] for x,y in zip(c,b))}


def evaluate(root, candidate, output, *, baseline=None, partition='validation', initial_probe='I1', prompts=None, max_cases=None, allow_live_judge=False, trust_artifacts=False):
    """Use the candidate's verified panel split; compare identical case IDs and inputs."""
    root,output=Path(root),Path(output)
    need(trust_artifacts, 'Only execute trusted team artifacts; pass --trust-artifacts')
    need(partition in ('validation','test'), 'Choose validation or test')
    need(not output.exists(), 'Evidence output already exists')
    need(max_cases is None or type(max_cases) is int and 1<=max_cases<=5000, 'Invalid max_cases')
    reg=a.existing(root); c=artifact_info(reg,candidate); check_review_only(c)
    b=artifact_info(reg,baseline) if baseline else None
    if b:
        need(b.adapter==c.adapter and b.artifact_id!=c.artifact_id, 'Compare different versions of the same adapter')
        check_lora(b)
    p=c.provenance
    did,sid=p.get('training_dataset_id'),p.get('split_id')
    need(isinstance(did,str) and isinstance(sid,str),'Candidate needs dataset and split provenance')
    info=d.inspect_snapshot(root,did,sid)
    need(info['split_algorithm']==d.PANEL_ALGORITHM,'Release comparison currently requires a fixed-panel split')
    need(info['dataset_manifest_sha256']==p.get('dataset_manifest_sha256') and info['split_manifest_sha256']==p.get('split_manifest_sha256'),'Candidate provenance mismatch')
    judge=None
    if c.adapter=='harness':
        judge=c.options['judge_provider'] if allow_live_judge else 'mock'
        if allow_live_judge:
            need(max_cases is not None,'Live judge requires explicit case budget and consent')
            need(judge in ('google','openai'),'Unsupported live judge')
            if b: need((b.options.get('judge_provider'),b.options.get('judge_model'))==(judge,c.options.get('judge_model')),'Judge provider/model must match for paired comparison')
    else:
        need(not allow_live_judge,'Judge consent only applies to Harness')
    pool=info['probe_pool']
    # Prompt text is not stored in raw rows. Use the supplied collection definition,
    # verify the adapter's bound prompts against it, and record its hash.
    prompts=Path(prompts) if prompts else root/'models/harness/v2/collector/prompts/fingerprinting_prompts.yaml'
    import yaml
    raw=yaml.safe_load(prompts.read_text(encoding='utf-8'))
    defs={q['id']:q['text'] for q in raw['prompts']}
    need(set(pool)<=set(defs) and initial_probe in pool,'Missing panel prompt definitions or initial probe')
    cs=_strategy(root,reg,c,judge);bs=_strategy(root,reg,b,judge) if b else None
    for s in (cs,bs):
        if s:
            for q in s.identifiers[0].required_probes():
                need(q.probe_id in pool and defs[q.probe_id]==q.prompt_text,'Required probe absent or prompt definition mismatch')
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'partition.jsonl';d.export(root,did,sid,partition,path)
        traces=load_traces(path,pool,info['prompt_set_version'])
    # Each panel is one case for RF/Harness, each response a case for LoRA.
    groups={k:[t for t in traces if t['model_id']==k] for k in sorted({t['model_id'] for t in traces})}
    ordered=[rs[i] for i in range(max(map(len,groups.values()))) for rs in groups.values() if i<len(rs)]
    cases=[]
    for t in ordered:
        obs={pid:Observation(defs[pid], t['answers'][pid], pid, completed_blank=not t['answers'][pid].strip()) for pid in pool}
        for pid in (pool if c.adapter=='lora' else [initial_probe]):
            key=t['model_id'];cid=stable_hash([t['record_ids'][x] for x in sorted(pool)]+[pid]);
            cases.append(EvaluationCase(cid,FingerprintRequest(cid,obs[pid]),key,reg.catalog.get(key).family_id,did,sid,replay_probes=obs,persona_id=t['persona_id'],source_record_ids=[t['record_ids'][x] for x in (pool if c.adapter!='lora' else [pid])]))
    total=len(cases)
    if judge=='mock' and max_cases is None: max_cases=3
    cases=cases[:max_cases] if max_cases else cases
    def run(s):
        result=EvaluationRunner.stage2(cases,s)
        rows=[]
        for r in result.rows:
            x=r['attempts'][0]
            pred=x['candidate_model']; accepted=x['accepted_model']
            # No raw responses, judge reasons, credentials or provider metadata in reports.
            rows.append({'case_id':r['case_id'],'actual_model':r['actual_model'],'candidate_model':pred,'accepted_model':accepted,'outcome':x['outcome'],'score':x['score'],'score_type':x['score_type'],'duration_ms':x['duration_ms'],'additional_probes':len(r['probes_collected'])})
        return rows
    cr=run(cs);br=run(bs) if bs else None
    # Mock output is plumbing only: do not publish or report accuracy.
    mock=judge=='mock'
    def report(m,rows):
        return {'artifact_id':m.artifact_id,'manifest_sha256':m.manifest_sha256,'supported_models':list(m.supported_models),
                'metrics':({'cases':len(rows),'errors':sum(r['outcome']=='error' for r in rows)} if mock else summarize(rows,reg.catalog)),
                'rows':([] if mock else rows)}
    present={x.actual_model_id for x in cases}; common=present & set(c.supported_models) & (set(b.supported_models) if b else set())
    result={'schema':SCHEMA,'created_at':now(),'environment':evidence_environment(root),'dataset_id':did,'split_id':sid,'dataset_manifest_sha256':info['dataset_manifest_sha256'],'split_manifest_sha256':info['split_manifest_sha256'],'partition':partition,
            'case_unit':'single_response' if c.adapter=='lora' else 'reconstructed_panel','initial_probe':None if c.adapter=='lora' else initial_probe,'prompt_definitions_sha256':stable_hash({x:defs[x] for x in pool}),
            'case_ids_sha256':stable_hash([x.case_id for x in cases]),'available_cases':total,'evaluated_cases':len(cases),'complete_partition':len(cases)==total,'judge_provider':judge,'judge_model':c.options.get('judge_model') if judge else None,'mock_only':mock,
            'target_api_calls':0,'independent_holdout_certified':False,'unknown_family_evaluated':False,'candidate':report(c,cr),'baseline':report(b,br) if b else None,
            'shared_label_comparison':_paired_metrics(cr,br,common,reg.catalog) if b and not mock else None,
            'coverage':{'cohort_models':sorted(present),'candidate_missing_models':sorted(present-set(c.supported_models)),'candidate_untested_models':sorted(set(c.supported_models)-present),'baseline_missing_models':sorted(present-set(b.supported_models)) if b else None},
            'limitations':['Validation may have been used for model/prompt selection; test is exploratory, not certified independent.', 'Historical training/reference overlap has not been certified absent.', 'Legacy RF input uses one predeclared probe without backend metadata; panel methods have more evidence.', 'Fixed known probes and reconstructed traces, not arbitrary user questions or independent sessions.', 'Candidate accuracy is not accepted-identity accuracy; no thresholds calibrated.']}
    a.write_new(output,a.json_text(result));return result


def _profile(root, config):
    """Validate the same restrictions as the live Stage 2 worker without paid calls."""
    reg=a.existing(root);cfg=load_pipeline_config(config,reg)
    need(not cfg.stage1.enabled and not cfg.cards_enabled,'Stage 1 and automatic cards must be off')
    defs={};hashes={}
    for choice in cfg.stage2.methods:
        m=artifact_info(reg,choice.artifact_id);check_review_only(m);hashes[m.artifact_id]=m.manifest_sha256
        strategy=_strategy(root,reg,m,'mock' if m.adapter=='harness' else None)
        for q in strategy.identifiers[0].required_probes():
            need(defs.setdefault(q.probe_id,q.prompt_text)==q.prompt_text,'Conflicting probe definitions')
    need(len(defs)<=6 and 'UI-INITIAL' not in defs,'Prototype probe budget exceeded')
    return cfg,hashes


def _release_dir(root, name):
    need(isinstance(name,str) and re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}',name),'Invalid release ID')
    directory=root/'.local/releases'/name
    need(directory.resolve().is_relative_to(root.resolve()) and not directory.is_symlink(),'Unsafe release path')
    return directory


def _save_release(root, name, snapshot, receipt, evidence=None):
    import yaml
    dest=_release_dir(root,name);need(not dest.exists(),'Release ID already exists')
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'pipeline.yaml';path.write_text(yaml.safe_dump(snapshot,sort_keys=False),encoding='utf-8')
        cfg,hashes=_profile(root,path)
        receipt={**receipt,'release_id':name,'created_at':now(),'artifact_manifest_sha256':hashes,'config_sha256':cfg.config_sha256,'pipeline_file_sha256':a.digest(path),'activated':False}
        dest.mkdir(parents=True,exist_ok=False)
        try:
            a.write_new(dest/'pipeline.yaml',path.read_text(encoding='utf-8'))
            if evidence is not None:
                a.write_new(dest/'evaluation.json',evidence)
                receipt['evaluation_sha256']=a.digest(dest/'evaluation.json')
            a.write_new(dest/'receipt.json',a.json_text(receipt))
        except Exception:
            import shutil
            shutil.rmtree(dest);raise
    return {**receipt,'config_path':str(dest/'pipeline.yaml')}


def publish(root, evidence_path, base_config, name, *, review_note, acknowledge_exploratory=False, acknowledge_regression=False):
    root=Path(root); evidence_path=Path(evidence_path); r=a.read_json(evidence_path)
    need(r.get('schema')==SCHEMA and r.get('mock_only') is False and r.get('complete_partition') is True,'Require complete, non-mock evaluation evidence')
    need(acknowledge_exploratory and isinstance(review_note,str) and len(review_note.strip())>=15,'Explicit exploratory review and substantive note required')
    need(r['environment']==evidence_environment(root),'Evaluation environment/catalog/source changed; rerun evaluation')
    reg=a.existing(root); c=artifact_info(reg,r['candidate']['artifact_id']);check_review_only(c)
    need(c.manifest_sha256==r['candidate']['manifest_sha256'],'Candidate manifest changed')
    info=d.inspect_snapshot(root,r['dataset_id'],r['split_id'])
    need(info['dataset_manifest_sha256']==r['dataset_manifest_sha256'] and info['split_manifest_sha256']==r['split_manifest_sha256'],'Evaluation dataset/split changed')
    need(c.provenance.get('dataset_manifest_sha256')==info['dataset_manifest_sha256'] and c.provenance.get('split_manifest_sha256')==info['split_manifest_sha256'],'Candidate provenance changed')
    need(r.get('partition') in ('validation','test') and info['split_algorithm']==d.PANEL_ALGORITHM,'Invalid release protocol')
    # Reconstruct the complete ordered cohort from the verified snapshot; counters
    # in a report alone cannot establish completeness. No model calls here.
    with tempfile.TemporaryDirectory() as td:
        data=Path(td)/'partition.jsonl';d.export(root,r['dataset_id'],r['split_id'],r['partition'],data)
        traces=load_traces(data,info['probe_pool'],info['prompt_set_version'])
    groups={k:[t for t in traces if t['model_id']==k] for k in sorted({t['model_id'] for t in traces})}
    ordered=[rs[i] for i in range(max(map(len,groups.values()))) for rs in groups.values() if i<len(rs)]
    pool=info['probe_pool'];initial=r['initial_probe']
    need(c.adapter=='lora' or initial in pool,'Invalid initial probe')
    expected=[(stable_hash([t['record_ids'][x] for x in sorted(pool)]+[pid]),t['model_id']) for t in ordered for pid in (pool if c.adapter=='lora' else [initial])]
    rows=r['candidate']['rows']; metrics=summarize(rows,reg.catalog)
    need([(x['case_id'],x['actual_model']) for x in rows]==expected,'Evaluation does not match complete pinned cohort')
    need(all(x['candidate_model'] in c.supported_models for x in rows),'Prediction outside candidate label space')
    need(metrics==r['candidate']['metrics'] and len(rows)==r['available_cases']==r['evaluated_cases'] and stable_hash([x['case_id'] for x in rows])==r['case_ids_sha256'],'Evaluation rows/metrics inconsistent')
    need(metrics['errors']==metrics['missing_predictions']==metrics['accepted']==0,'Candidate must run without errors, missing predictions or accepted identities')
    need(set(metrics['class_counts'])==set(c.supported_models),'All candidate and cohort labels must be covered')
    base,oldhashes=_profile(root,Path(base_config));snap=base.snapshot(); prior=next((x['artifact'] for x in snap['stage2']['methods'] if x['adapter']==c.adapter),None)
    b=r.get('baseline'); paired=r.get('shared_label_comparison')
    if b:
        bm=artifact_info(reg,b['artifact_id']);need(bm.adapter==c.adapter and bm.manifest_sha256==b['manifest_sha256'],'Baseline changed')
        need(set(bm.supported_models)<=set(c.supported_models),'Candidate loses previously supported identities')
        need(summarize(b['rows'],reg.catalog)==b['metrics'],'Baseline metrics inconsistent')
        need([(x['case_id'],x['actual_model']) for x in b['rows']]==expected,'Baseline cohort mismatch')
        need(b['metrics']['errors']==0,'Baseline execution failed; comparison is not reliable')
        common=set(metrics['class_counts']) & set(bm.supported_models) & set(c.supported_models)
        need(paired is not None and paired==_paired_metrics(rows,b['rows'],common,reg.catalog),'Missing or inconsistent shared-label comparison')
        need(all(x>=0 for x in paired['delta'].values()) or acknowledge_regression,'Shared-label regression needs explicit acknowledgement')
    need(prior is None or prior==c.artifact_id or b and prior==b['artifact_id'],'Comparison must use the selected predecessor (or already selected candidate)')
    methods={x['adapter']:x for x in snap['stage2']['methods']};methods[c.adapter]={'adapter':c.adapter,'artifact':c.artifact_id}
    snap['stage2']={'mode':'single' if len(methods)==1 else 'fallback','methods':[methods[k] for k in ORDER if k in methods]}
    snap['pipeline']['name']='review_release_'+name
    return _save_release(root,name,snap,{'action':'publish_review_profile','review_note':review_note.strip(),'acknowledge_exploratory':True,'acknowledge_regression':acknowledge_regression,'previous_config':base.snapshot(),'previous_artifact_manifest_sha256':oldhashes,'candidate_artifact':c.artifact_id,'evaluation_partition':r['partition'],'independent_holdout_certified':False}, evidence_path.read_text(encoding='utf-8'))


def rollback(root, source, name, *, review_note):
    root=Path(root);src=_release_dir(root,source);r=a.read_json(src/'receipt.json')
    need(r.get('release_id')==source and r.get('pipeline_file_sha256')==a.digest(src/'pipeline.yaml'),'Release receipt/config mismatch')
    if 'evaluation_sha256' in r:need(r['evaluation_sha256']==a.digest(src/'evaluation.json'),'Release evidence changed')
    need(isinstance(review_note,str) and len(review_note.strip())>=15,'Substantive rollback note required')
    old=r['previous_config'];reg=a.existing(root)
    for aid,sha in r['artifact_manifest_sha256'].items():need(artifact_info(reg,aid).manifest_sha256==sha,'Published artifact changed')
    for aid,sha in r['previous_artifact_manifest_sha256'].items():need(artifact_info(reg,aid).manifest_sha256==sha,'Prior artifact changed')
    return _save_release(root,name,old,{'action':'rollback_review_profile','source_release':source,'review_note':review_note.strip(),'previous_config':load_pipeline_config(src/'pipeline.yaml',reg).snapshot(),'previous_artifact_manifest_sha256':r['artifact_manifest_sha256']})


def history(root):
    directory=Path(root)/'.local/releases'
    return [a.read_json(p) for p in sorted(directory.glob('*/receipt.json'))]


def evaluate_run(root, run_id, base_config, *, trust_artifacts=False, output_dir=None, prompts=None):
    """Automatically evaluate registered training outputs; never use a live judge or test split."""
    root=Path(root)
    need(trust_artifacts,'Only execute trusted team artifacts')
    need(isinstance(run_id,str) and re.fullmatch('[0-9a-f]{32}',run_id),'Invalid training run ID')
    tr=a.read_json(root/'.local/training_runs'/run_id/'result.json')
    need(tr.get('run_id')==run_id,'Training run identity mismatch')
    reg=a.existing(root);base=load_pipeline_config(base_config,reg)
    need(not base.stage1.enabled,'Stage 1 deferred')
    prior={x.adapter:x.artifact_id for x in base.stage2.methods}
    dest=Path(output_dir) if output_dir else root/'.local/training_runs'/run_id/'release_evaluation'
    dest.mkdir(parents=True,exist_ok=False)
    results={}
    for method,spec in tr['methods'].items():
        if spec['status']!='registered_candidate':
            results[method]={'status':'skipped','reason':spec['status']};continue
        if method=='harness':
            results[method]={'status':'needs_explicit_judge_review','reason':'No automatic billable judge calls; run release evaluate with explicit consent.'};continue
        if method not in ('random_forest','lora'):
            results[method]={'status':'skipped','reason':'Stage 1 deferred'};continue
        try:
            aid=spec['artifact_id'];m=artifact_info(reg,aid)
            need(m.provenance.get('training_run_id')==run_id,'Artifact is not bound to this run')
            previous=prior.get(method)
            if previous==aid:previous=None
            output=dest/(method+'.json')
            # A provisional old LoRA cannot be compared: operator must explicitly
            # choose a first validated release instead of silently scoring it.
            # RF training records the exact full candidate prompt definitions.
            # Other methods can provide a collection YAML explicitly.
            definitions=spec.get('parameters',{}).get('prompt_definitions') if method=='random_forest' else None
            if prompts is None and definitions:
                import yaml
                with tempfile.TemporaryDirectory() as td:
                    prompt_file=Path(td)/'prompts.yaml'
                    prompt_file.write_text(yaml.safe_dump({'prompts':[{'id':k,'text':v} for k,v in definitions.items()]},allow_unicode=True),encoding='utf-8')
                    result=evaluate(root,aid,output,baseline=previous,trust_artifacts=True,prompts=prompt_file,initial_probe='I1' if 'I1' in definitions else sorted(definitions)[0])
            else:
                result=evaluate(root,aid,output,baseline=previous,trust_artifacts=True,prompts=prompts)
            results[method]={'status':'evaluated','evidence':str(output),'candidate_metrics':result['candidate']['metrics'],'shared_label_comparison':result['shared_label_comparison']}
        except Exception as exc:
            results[method]={'status':'blocked','error_type':type(exc).__name__,'reason':str(exc)[:350]}
    report={'training_run_id':run_id,'methods':results,'auto_activated':False,'partition':'validation'}
    a.write_new(dest/'summary.json',a.json_text(report));return report
