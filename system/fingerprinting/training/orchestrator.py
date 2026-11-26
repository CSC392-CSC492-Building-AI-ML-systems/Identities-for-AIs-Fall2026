"""Shared training lifecycle. Method-specific fitting is supplied by trusted strategies.

No dynamic imports from config, external shell commands, automatic deployment or test
partition access. This is a local developer tool, not an isolation/sandbox boundary.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Mapping, Any
import uuid
import json

from ..onboarding import datasets as d, artifacts as a
from ..registry import ARTIFACT_RE

METHODS = ('random_forest','harness','lora','logistic_regression')

class TrainingError(ValueError):
    pass

class UnchangedCandidate(Exception):
    """Trusted trainer found an identical, file-ready candidate; no new version."""
    def __init__(self, artifact_ids):
        self.artifact_ids = list(artifact_ids)
        super().__init__("Reference content and settings unchanged")

def require(ok, message):
    if not ok: raise TrainingError(message)

@dataclass(frozen=True)
class TrainingContext:
    method: str
    artifact_id: str
    dataset_id: str
    split_id: str
    dataset_manifest_sha256: str
    split_manifest_sha256: str
    eligibility_policy: str
    train_jsonl: Path
    validation_jsonl: Path
    output_dir: Path
    parameters: dict[str, Any]
    split_algorithm: str | None = None
    probe_pool: list[str] | None = None
    prompt_set_version: str | None = None
    system_root: Path | None = None

class TrainingStrategy(Protocol):
    def run(self, context: TrainingContext) -> None:
        """Prepare, fit/build, validate and export a candidate bundle into output_dir.

        Supply manifest.json, declared payload files, training code revision,
        dependencies, preprocessing and validation evidence. Never train on
        validation; the test/calibration partitions are not provided here.
        """
        ...

# Register trusted, reviewed Python implementations here when teammate contracts
# are available. No mock trainer is installed in the developer CLI.
def available_trainers() -> dict[str, TrainingStrategy]:
    from .random_forest import RandomForestTrainer
    from .lora import LoRATrainer
    from .harness import HarnessTrainer
    return {"random_forest": RandomForestTrainer(), "lora": LoRATrainer(), "harness": HarnessTrainer()}

def _now(): return datetime.now(timezone.utc).isoformat()

def read_config(path: Path):
    return a.read_json(path)

def plan(root: Path, config: dict, trainers: Mapping[str, TrainingStrategy], method: str | None = None):
    require(set(config)=={'dataset_id','split_id','methods'}, 'Expected dataset_id, split_id and methods only')
    dataset_id,split_id=config['dataset_id'],config['split_id']
    require(isinstance(dataset_id,str) and isinstance(split_id,str),'Dataset and split IDs must be strings')
    methods=config['methods']
    require(isinstance(methods,dict) and methods and set(methods)<=set(METHODS),'Unknown/empty training methods')
    require(method is None or method in methods,'Selected method is not in config')
    # Validate entire configuration, even if one method is selected.
    registry=a.existing(root)
    for name,spec in methods.items():
        require(isinstance(spec,dict) and set(spec)=={'artifact_id','parameters'},f'{name}: expected artifact_id and parameters')
        aid=spec['artifact_id']
        require(isinstance(aid,str) and ARTIFACT_RE.fullmatch(aid) and aid.split('/')[0]==a.PREFIX[name],f'{name}: invalid artifact ID')
        a.safe_rel(aid)
        require(isinstance(spec['parameters'],dict),f'{name}: parameters must be an object')
        # Reject non-JSON/nonfinite values from programmatic callers.
        json.dumps(spec['parameters'],allow_nan=False)
    info=d.inspect_snapshot(root,dataset_id,split_id)
    require(info['partitions']['train']['records']>0 and info['partitions']['validation']['records']>0,'Training and validation must be nonempty')
    results={}
    for name in METHODS:
        if name not in methods or (method is not None and name!=method): continue
        aid=methods[name]['artifact_id']
        occupied=aid.casefold() in {x.casefold() for x in registry.artifact_ids} or (root/'models'/aid).exists()
        supported=name in trainers and (not hasattr(trainers[name],'supports') or trainers[name].supports(info))
        results[name]={'artifact_id':aid,'status': 'blocked_stage1_deferred' if name=='logistic_regression' else 'blocked_existing_version' if occupied else 'ready' if supported else 'blocked_incompatible_split_protocol' if name in trainers else 'blocked_trainer_not_integrated',
                       'parameters':methods[name]['parameters']}
        if results[name]['status']=='ready' and hasattr(trainers[name],'check_parameters'):
            try: trainers[name].check_parameters(methods[name]['parameters'])
            except ValueError as exc: results[name].update(status='blocked_invalid_parameters', reason=str(exc))
    return {'schema_version':'1.0','dataset_id':dataset_id,'split_id':split_id,
            'dataset_manifest_sha256':info['dataset_manifest_sha256'],'split_manifest_sha256':info['split_manifest_sha256'],
            'eligibility_policy':info['eligibility_policy'],'partitions':info['partitions'],
            'split_algorithm':info.get('split_algorithm'),'probe_pool':info.get('probe_pool'),'prompt_set_version':info.get('prompt_set_version'),
            'independent_holdout_certified':False,'methods':results,'auto_activate':False}

def run(root: Path,config: dict,trainers: Mapping[str,TrainingStrategy],*,method=None,approve_dataset=False,register_candidates=False):
    require(approve_dataset is True,'Explicit --approve-dataset required for a local experimental run; not holdout certification')
    root=root.resolve(); planned=plan(root,config,trainers,method)
    run_id=uuid.uuid4().hex
    run_dir=root/'.local'/'training_runs'/run_id
    run_dir.mkdir(parents=True,exist_ok=False)
    report={**planned,'run_id':run_id,'started_at':_now(),'status':'running','register_candidates':register_candidates}
    # Retain a snapshot of the user configuration and plan, even if interrupted.
    a.write_new(run_dir/'plan.json',a.json_text(report))
    ready=[name for name,spec in planned['methods'].items() if spec['status']=='ready']
    report['methods']={name:dict(spec) for name,spec in planned['methods'].items()}
    if not ready:
        report['status']='blocked'
    else:
        try:
            # Export once per run, only train/validation. Trainers are trusted local
            # code, not sandboxed; never use test data during training/tuning.
            exports={p:d.export(root,planned['dataset_id'],planned['split_id'],p,run_dir/(p+'.jsonl')) for p in ('train','validation')}
            require(all(x['split_manifest_sha256']==planned['split_manifest_sha256'] for x in exports.values()),'Split changed during preparation')
            report['exports']=exports
            for name in ready:
                spec=report['methods'][name]; bundle=run_dir/name/'bundle';bundle.mkdir(parents=True)
                ctx=TrainingContext(name,spec['artifact_id'],planned['dataset_id'],planned['split_id'],planned['dataset_manifest_sha256'],planned['split_manifest_sha256'],planned['eligibility_policy'],run_dir/'train.jsonl',run_dir/'validation.jsonl',bundle,json.loads(json.dumps(spec['parameters'])),planned['split_algorithm'],planned['probe_pool'],planned['prompt_set_version'],root)
                try:
                    # Check that prior strategies have not mutated shared inputs.
                    require(all(a.digest(run_dir/(p+'.jsonl'))==exports[p]['sha256'] for p in exports),'Export changed by trainer')
                    trainers[name].run(ctx)
                    require(all(a.digest(run_dir/(p+'.jsonl'))==exports[p]['sha256'] for p in exports),'Trainer modified source exports')
                    current=d.inspect_snapshot(root,ctx.dataset_id,ctx.split_id)
                    require(current['dataset_manifest_sha256']==ctx.dataset_manifest_sha256 and current['split_manifest_sha256']==ctx.split_manifest_sha256,'Source dataset/split changed during training')
                    raw=a.read_json(bundle/'manifest.json')
                    require(raw.get('artifact_id')==ctx.artifact_id and raw.get('adapter')==name,'Trainer emitted wrong artifact identity')
                    require(set(raw.get('supported_models',[]))<=set(planned['partitions']['train']['models']),'Candidate includes classes absent from training split')
                    prov=raw.get('provenance');require(isinstance(prov,dict),'Trainer must supply provenance')
                    pinned={'training_dataset_id':ctx.dataset_id,'dataset_manifest_sha256':ctx.dataset_manifest_sha256,'split_id':ctx.split_id,'split_manifest_sha256':ctx.split_manifest_sha256,'eligibility_policy':ctx.eligibility_policy,'training_run_id':run_id}
                    for k,v in pinned.items():
                        require(k not in prov or prov[k]==v,f'Trainer provenance conflicts: {k}')
                        prov[k]=v
                    # No duplicate registry logic; candidate validation and registration
                    # both use the established artifact onboarding functions.
                    (bundle/'manifest.json').write_text(a.json_text(raw),encoding='utf-8')
                    checked=a.validate(root,bundle)
                    if register_candidates: checked=a.register(root,bundle,trust_bundle=True)
                    spec.update(status='registered_candidate' if register_candidates else 'candidate_validated',bundle=str(bundle.relative_to(root)),validation=checked)
                except UnchangedCandidate as exc:
                    # Only trusted trainer implementations may request reuse.
                    current=d.inspect_snapshot(root,ctx.dataset_id,ctx.split_id)
                    require(current['dataset_manifest_sha256']==ctx.dataset_manifest_sha256 and current['split_manifest_sha256']==ctx.split_manifest_sha256,'Source dataset/split changed during reuse check')
                    require(all(a.digest(run_dir/(p+'.jsonl'))==exports[p]['sha256'] for p in exports),'Export changed by trainer')
                    reg=a.existing(root)
                    require(bool(exc.artifact_ids) and all(reg.get(i).adapter==name and reg.readiness(i).ready for i in exc.artifact_ids),'Cannot reuse an unavailable candidate')
                    spec.update(status='skipped_unchanged',reusable_artifacts=exc.artifact_ids,reason=str(exc))
                except Exception as exc:
                    # Keep partial artifacts for local inspection; never register a failure.
                    spec.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:500])
            statuses=[s['status'] for s in report['methods'].values()]
            report['status']='completed' if all(s in ('registered_candidate','candidate_validated','skipped_unchanged') for s in statuses) else 'partial' if any(s in ('registered_candidate','candidate_validated','skipped_unchanged') for s in statuses) else 'failed'
        except Exception as exc:
            report['status']='failed';report['error_type']=type(exc).__name__;report['error']=str(exc)[:500]
        finally:
            # Temporary exported copies are not the authoritative raw snapshot.
            for p in ('train','validation'): (run_dir/(p+'.jsonl')).unlink(missing_ok=True)
    report['finished_at']=_now();a.write_new(run_dir/'result.json',a.json_text(report))
    return report

def history(root: Path):
    out=[]
    for folder in sorted((root/'.local'/'training_runs').glob('*')):
        if not folder.is_dir() or folder.is_symlink():continue
        result=folder/'result.json'; planned=folder/'plan.json'
        if result.is_file(): out.append(a.read_json(result))
        elif planned.is_file():out.append({**a.read_json(planned),'status':'incomplete_or_interrupted'})
    return out
