"""Validate and register candidate bundles without executing submitted code.

The existing registry is authoritative. Registration is not runtime validation,
scientific approval, or production activation. Only trusted team artifacts may
be registered: joblib and Harness source can execute code during later inference.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..config import load_pipeline_config
from ..model_catalog import ModelCatalog
from ..registry import ARTIFACT_RE, ArtifactRegistry

PREFIX = {'logistic_regression': 'stage1_lr', 'lora': 'lora',
          'harness': 'harness', 'random_forest': 'random_forest'}
PROVENANCE_FIELDS = ('source', 'training_dataset_id', 'split_id', 'training_code_revision')


class OnboardingError(ValueError):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise OnboardingError(message)


def read_json(path: Path) -> dict:
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, f'Duplicate JSON key: {k}')
            result[k] = v
        return result
    def invalid_constant(value):
        raise OnboardingError(f'Non-finite JSON constant: {value}')
    data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                      parse_constant=invalid_constant)
    need(isinstance(data, dict), f'{path.name}: expected JSON object')
    return data


def digest(path: Path) -> str:
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_new(path: Path, data: str) -> None:
    # Exclusive creation: no accidental overwrite of configuration or manifest.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        f.write(data)


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'


def safe_rel(value: Any) -> str:
    need(isinstance(value, str) and bool(value), 'File path must be a nonempty string')
    parts = value.split('/')
    need(all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', p) and not p.endswith('.')
             and p.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',
                  *[f'COM{i}' for i in range(1,10)], *[f'LPT{i}' for i in range(1,10)]}
             for p in parts), f'Unsafe or nonportable path: {value!r}')
    need(value != 'manifest.json', 'manifest.json is not a required payload file')
    return value


def inventory(source: Path) -> set[str]:
    need(source.is_dir() and not source.is_symlink(), 'Bundle must be an extracted, non-symlink directory')
    files = set()
    for path in source.rglob('*'):
        need(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(),
             f'Symlink/junction is not permitted: {path.name}')
        if path.is_dir():
            continue
        need(path.is_file(), f'Nonregular file: {path.name}')
        rel = path.relative_to(source).as_posix()
        if rel != 'manifest.json':
            safe_rel(rel)
        files.add(rel)
    need(len({p.casefold() for p in files}) == len(files), 'Case-insensitive path collision')
    return files


def existing(root: Path):
    catalog = ModelCatalog.from_file(root / 'catalog/models.json')
    return ArtifactRegistry(root, catalog)


def ensure_candidate(raw: dict, registry: ArtifactRegistry) -> str:
    aid = raw.get('artifact_id')
    need(isinstance(aid, str) and bool(ARTIFACT_RE.fullmatch(aid)), 'Invalid artifact_id')
    adapter = raw.get('adapter')
    need(isinstance(adapter, str) and adapter in PREFIX and aid.split('/')[0] == PREFIX[adapter],
         'Artifact ID prefix must match adapter (stage1_lr, lora, harness, random_forest)')
    safe_rel(aid)
    need(aid.casefold() not in {x.casefold() for x in registry.artifact_ids},
         f'Artifact {aid} is already registered; choose a new version')
    destination = registry.root / 'models' / aid
    need(not destination.exists() and not destination.is_symlink(), f'Artifact destination already exists: {aid}')
    for parent in (registry.root / 'models', destination.parent):
        need(not parent.is_symlink() and not getattr(parent, 'is_junction', lambda: False)(),
             'Artifact destination must not be a symlink/junction')
    return aid


def provenance_checks(raw: dict, root: Path) -> list[str]:
    p = raw.get('provenance')
    need(isinstance(p, dict), 'provenance must be an object')
    for name in PROVENANCE_FIELDS:
        need(isinstance(p.get(name), str) and bool(p[name].strip()) and not p[name].startswith('TODO'),
             f'provenance.{name} must be supplied by the teammate')
    deps = p.get('runtime_dependencies')
    need(isinstance(deps, dict) and bool(deps) and all(isinstance(k,str) and k.strip() and
         isinstance(v,str) and v.strip() and not v.startswith('TODO') for k,v in deps.items()),
         'provenance.runtime_dependencies must declare dependency versions')
    expected = p.get('dataset_manifest_sha256')
    need(isinstance(expected, str) and bool(re.fullmatch('[0-9a-f]{64}', expected)),
         'provenance.dataset_manifest_sha256 must be a SHA-256 digest')
    # Existing raw dataset manifests are not a dataset registry. Match a local
    # manifest if present, otherwise explicitly report that provenance is external.
    found = []
    for path in (root / 'datasets').rglob('manifest.json'):
        if path.is_file() and not path.is_symlink() and read_json(path).get('dataset_id') == p['training_dataset_id']:
            found.append(path)
    if found:
        need(len(found) == 1 and digest(found[0]) == expected, 'Local dataset manifest hash does not match provenance')
        split_sha=p.get('split_manifest_sha256')
        if split_sha is not None:
            from .datasets import inspect_snapshot
            need(isinstance(split_sha,str) and bool(re.fullmatch('[0-9a-f]{64}',split_sha)), 'Invalid split_manifest_sha256')
            info=inspect_snapshot(root,p['training_dataset_id'],p['split_id'])
            need(info['split_manifest_sha256']==split_sha,'Local split manifest hash does not match provenance')
            need(p.get('eligibility_policy',info['eligibility_policy'])==info['eligibility_policy'],'Local split eligibility policy mismatch')
            return ['Local raw snapshot and split assignment verified; training claims and holdout independence remain unverified.']
        return ['Dataset manifest digest matched locally; split membership and training claims are not verified.']
    return ['Dataset manifest not present locally; provenance hash is declared but not verified.']


def adapter_checks(m) -> list[str]:
    """Static/metadata checks only. Never import code from the submitted bundle."""
    o, root = m.options, m.directory
    files = {x.relative_path for x in m.required_files}
    def require(names):
        missing = set(names) - files
        need(not missing, f'Missing required adapter payloads: {sorted(missing)}')
    def review_only():
        need(o.get('acceptance_policy') == {'mode': 'review_only'},
             'New LoRA/RF candidates must use review_only until separately validated')
    if m.adapter == 'logistic_regression':
        from ..adapters.logistic_regression import FAMILIES, MODEL_TO_FAMILY, ALLOWED_APPROACHES
        need(set(m.supported_models) == set(MODEL_TO_FAMILY),
             'Stage 1 adapter upgrade required: current verifier supports only four Gemini/Llama identities')
        approaches = o.get('approaches')
        need(isinstance(approaches, list) and bool(approaches) and set(approaches) <= ALLOWED_APPROACHES,
             'Invalid Stage 1 approaches')
        need(o.get('decision_policy') == 'strict_two_check', 'Incompatible Stage 1 decision policy')
        require(['family_gemini_vs_llama.joblib'] + [f'{f}_conditional_{ids[0]}.joblib' for f,ids in FAMILIES.items()])
        if 'ovr_direct' in approaches:
            require([f'ovr_{x}.joblib' for x in m.supported_models])
        for a in approaches:
            for model in m.supported_models:
                name = f'{a}_{model}_threshold.json'
                require([name]); t = read_json(root/name); value = t.get('validation_threshold')
                need(t.get('target') == model and t.get('approach') == a and t.get('algorithm') == 'baseline_lr'
                     and type(value) in (int,float) and math.isfinite(value) and 0 < value <= 1,
                     f'Invalid threshold metadata: {name}')
        return ['Stage 1 binary estimators, serialization compatibility and thresholds need trusted runtime parity/evaluation.']
    if m.adapter == 'lora':
        from ..adapters.lora import LoRAIdentifier
        review_only(); require(['adapter_model.safetensors','adapter_config.json'])
        LoRAIdentifier(m)  # metadata only, no model load
        need(isinstance(o.get('base_model_revision'), str) and bool(re.fullmatch('[0-9a-f]{40}',o['base_model_revision'])),
             'LoRA base_model_revision must be a pinned 40-character commit')
        need(o.get('label_order_status') in ('confirmed','provisional_unconfirmed'), 'Declare label_order_status explicitly')
        if o['label_order_status'] == 'confirmed':
            need(isinstance(m.provenance.get('label_order_evidence'),str) and bool(m.provenance['label_order_evidence'].strip()),
                 'Confirmed class order requires teammate evidence in provenance.label_order_evidence')
        cfg = read_json(root/'adapter_config.json')
        need(cfg.get('task_type') == 'SEQ_CLS' and cfg.get('peft_type') == 'LORA' and
             cfg.get('base_model_name_or_path') == o.get('base_model'), 'PEFT type, task or base model mismatch')
        for opt,key in [('lora_rank','r'),('lora_alpha','lora_alpha')]:
            need(type(o.get(opt)) in (int,float) and o[opt] > 0 and cfg.get(key) == o[opt], f'LoRA {opt} mismatch')
        need(isinstance(o.get('base_model'),str) and o['base_model'].startswith('Qwen/Qwen2.5-'),
             'LoRA adapter upgrade/review required for a different base architecture')
        from safetensors import safe_open
        with safe_open(root/'adapter_model.safetensors', framework='numpy', device='cpu') as sf:
            heads = [k for k in sf.keys() if k.endswith('score.weight')]
            need(len(heads) == 1, 'Expected exactly one trained score.weight head')
            shape = list(sf.get_slice(heads[0]).get_shape())
            need(len(shape) == 2 and shape[0] == len(m.supported_models) and shape[1] > 0 and
                 shape == o.get('classifier_head_shape'), 'Classification head shape or label count mismatch')
            need(any('lora_A' in k for k in sf.keys()) and any('lora_B' in k for k in sf.keys()), 'Missing LoRA matrices')
        return ['LoRA checkpoint metadata checked; base weights, label evidence and inference parity still need runtime validation.']
    if m.adapter == 'random_forest':
        from ..adapters.random_forest import RandomForestIdentifier
        from ..adapters import rf_features
        review_only(); require(['classifier.joblib','feature_manifest.json','feature_extractor.py'])
        from ..adapters import rf_panel_features
        if o.get('feature_abi') == rf_panel_features.FEATURE_ABI:
            from ..adapters.random_forest_panel import RandomForestPanelIdentifier
            require(['base_text_features.py','validation_report.json'])
            need((root/'feature_extractor.py').read_bytes()==Path(rf_panel_features.__file__).read_bytes() and
                 (root/'base_text_features.py').read_bytes()==Path(rf_features.__file__).read_bytes(),
                 'Panel RF feature implementation differs from installed source')
            RandomForestPanelIdentifier(m)
            need(isinstance(o.get('sklearn_version'),str) and bool(o['sklearn_version'].strip()),'Specify sklearn_version')
            return ['Panel RF feature ABI and probe definitions checked; runtime and open-set validation remain required.']
        need((root/'feature_extractor.py').read_bytes() == Path(rf_features.__file__).read_bytes(),
             'Random Forest adapter upgrade required: feature extractor differs from current installed source')
        RandomForestIdentifier(m)  # metadata only, no joblib load
        need(len(o['label_order']) == len(set(o['label_order'])), 'Duplicate RF label order')
        need(isinstance(o.get('sklearn_version'),str) and bool(o['sklearn_version'].strip()), 'Specify sklearn_version')
        return ['RF feature ABI checked; trusted joblib inference must verify class order, estimator feature names and sklearn version.']
    if m.adapter == 'harness':
        from ..adapters.harness import HarnessIdentifier
        v2 = o.get('reference_abi') == 'catalog_reference_v2'
        require(['agent/identify_api.py','agent/identify.py','agent/probe_identify.py','agent/check_chatbot.py',
                 'collector/prompts/fingerprinting_prompts.yaml'])
        if v2:
            require(['reference_report.json'])
        else:
            require(['agent/card_lookup.py','cards/cardlib.py','collector/licences.yaml','collector/models.yaml',
                     'collector/prompts/personas.yaml'] + [f'cards/fields/{d}.yaml' for d in ('compliance','governance','evaluation','risk')])
        HarnessIdentifier(m, judge_provider='mock')  # YAML/metadata only
        # Original Harness has literal MODELS and DEFAULT_PROBES. No exec/import.
        tree = ast.parse((root/'agent/identify.py').read_text(encoding='utf-8'))
        model_maps = [ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                      and any(isinstance(t,ast.Name) and t.id=='MODELS' for t in n.targets)]
        need(len(model_maps)==1 and isinstance(model_maps[0],dict) and set(model_maps[0])==set(m.supported_models),
             'Harness source MODELS and manifest disagree, or source contract changed')
        probe_tree = ast.parse((root/'agent/probe_identify.py').read_text(encoding='utf-8'))
        declared_probes = [ast.literal_eval(n.value) for n in probe_tree.body if isinstance(n,ast.Assign)
                           and any(isinstance(t,ast.Name) and t.id=='DEFAULT_PROBES' for t in n.targets)]
        need(declared_probes == [o['probe_ids']], 'Harness source DEFAULT_PROBES and manifest disagree')
        need(o.get('reference_split') == 'sample_index in {0,1} only',
             'Current Harness expects sample_index 0/1 reference-only data')
        for model in m.supported_models:
            name = f'collector/data/raw/{model}/fingerprint_v0.jsonl'; require([name]); covered=set(); counts={}; ids=set()
            with (root/name).open(encoding='utf-8') as f:
                for line in f:
                    row=json.loads(line)
                    need(isinstance(row,dict) and row.get('model_key')==model, f'Reference model mismatch: {name}')
                    need(type(row.get('sample_index')) is int and row['sample_index'] in (0,1),
                         f'Non-reference sample_index found in {name}; exclude held-out rows')
                    need(row.get('prompt_id') in o['probe_ids'], f'Unexpected reference prompt in {name}')
                    if v2:
                        need(row.get('error') is None and (row.get('response_text') is None or isinstance(row.get('response_text'),str)), 'Invalid v2 reference response')
                        rid=row.get('record_id'); need(isinstance(rid,str) and rid not in ids,'Missing or duplicate v2 reference ID'); ids.add(rid)
                        pid=row['prompt_id']; counts[pid]=counts.get(pid,0)+1
                        if counts[pid]>=4: covered.add(pid)
                    elif not row.get('error') and isinstance(row.get('response_text'),str) and row['response_text'].strip():
                        covered.add(row.get('prompt_id'))
            need(set(o['probe_ids']) <= covered, f'Missing usable reference probes for {model}')
        return ['Harness source and reference coverage checked, not executed; reference leakage, rule behavior and real judge still require validation.']
    raise OnboardingError('Unsupported adapter')


def stage_bundle(root: Path, source: Path, scratch: Path) -> tuple[Path, dict]:
    reg = existing(root)
    found = inventory(source)
    need('manifest.json' in found, 'Bundle needs manifest.json')
    raw = read_json(source/'manifest.json')
    aid = ensure_candidate(raw, reg)
    rows = raw.get('required_files')
    need(isinstance(rows,list) and bool(rows) and all(isinstance(x,dict) for x in rows),'required_files must be nonempty')
    names = [safe_rel(x.get('path')) for x in rows]
    need(len(set(names)) == len(names), 'Duplicate declared payload path')
    need(found == set(names)|{'manifest.json'}, f'Bundle inventory mismatch; missing={sorted(set(names)-found)}, undeclared={sorted(found-set(names)-{"manifest.json"})}')
    warnings = provenance_checks(raw,root)
    dest = scratch/'models'/aid; dest.mkdir(parents=True)
    for item,name in zip(rows,names):
        out = dest/name; out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,out)
        actual=digest(out); supplied=item.get('sha256')
        need(supplied is None or supplied==actual, f'Checksum mismatch: {name}')
        item['sha256']=actual
    raw['provenance']['onboarding_status']='candidate_metadata_checked_runtime_pending'
    write_new(dest/'manifest.json', json_text(raw))
    (scratch/'catalog').mkdir(); shutil.copyfile(root/'catalog/models.json',scratch/'catalog/models.json')
    write_new(scratch/'models/registry.json',json_text({'schema_version':'1.0','artifacts':{aid:f'models/{aid}/manifest.json'}}))
    staged=existing(scratch); manifest=staged.get(aid)
    need(staged.readiness(aid).ready, 'Staged registry readiness check failed')
    warnings+=adapter_checks(manifest)
    report={'artifact_id':aid,'adapter':manifest.adapter,'supported_models':list(manifest.supported_models),
            'payload_files':len(names),'manifest_sha256':manifest.manifest_sha256,'status':'metadata_checked',
            'runtime_validated':False,'activated':False,'warnings':warnings}
    return dest,report


@contextmanager
def registry_lock(root: Path):
    path=root/'models/.onboarding.lock'
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc:
        raise OnboardingError('Onboarding locked; another process may be writing the registry. See guide.') from exc
    try:
        os.close(fd); yield
    finally:
        path.unlink(missing_ok=True)


def validate(root: Path, source: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix='fingerprint-onboard-') as tmp:
        _,report=stage_bundle(root.resolve(),source,Path(tmp)); return report


def register(root: Path, source: Path, *, trust_bundle: bool=False) -> dict:
    need(trust_bundle, 'Registration requires --trust-bundle for reviewed team-owned artifacts')
    root=root.resolve()
    with registry_lock(root), tempfile.TemporaryDirectory(prefix='.onboarding-',dir=root/'models') as tmp:
        dest,report=stage_bundle(root,source,Path(tmp)); aid=report['artifact_id']
        registry=existing(root); index_path=root/'models/registry.json'; index=read_json(index_path)
        ensure_candidate(read_json(dest/'manifest.json'),registry)
        target=root/'models'/aid; target.parent.mkdir(parents=True,exist_ok=True)
        index['artifacts'][aid]=f'models/{aid}/manifest.json'
        new_index=Path(tmp)/'registry-next.json'; write_new(new_index,json_text(index))
        dest.rename(target)
        try:
            os.replace(new_index,index_path)
        except OSError:
            # Only roll back the newly staged directory, never an existing artifact.
            target.rename(dest); raise
        report['status']='registered_candidate'
        return report


def template(root: Path, source_id: str, new_id: str, output: Path, *, dataset_id: str|None=None, split_id: str|None=None) -> None:
    registry=existing(root); old=registry.get(source_id); raw=read_json(old.manifest_path)
    raw['artifact_id']=new_id; ensure_candidate(raw,registry)
    raw['required_files']=[{'path':x.relative_path,'sha256':None} for x in old.required_files]
    raw['provenance']={k:'TODO' for k in PROVENANCE_FIELDS}
    raw['provenance'].update(dataset_manifest_sha256='TODO',runtime_dependencies={'python':'TODO'})
    need((dataset_id is None)==(split_id is None), 'Provide both dataset_id and split_id or neither')
    if dataset_id is not None:
        from .datasets import inspect_snapshot
        info=inspect_snapshot(root,dataset_id,split_id)
        raw['provenance'].update(training_dataset_id=dataset_id,split_id=split_id,
            dataset_manifest_sha256=info['dataset_manifest_sha256'],split_manifest_sha256=info['split_manifest_sha256'],
            eligibility_policy=info['eligibility_policy'])
    if old.adapter in ('lora','random_forest'):
        raw['options']['acceptance_policy']={'mode':'review_only'}
    if old.adapter=='lora':
        raw['options']['base_model_revision']='TODO'; raw['options']['label_order_status']='provisional_unconfirmed'
    write_new(output,json_text(raw))


def candidate_config(root: Path, aid: str, output: Path, *, base: Path|None=None, single: bool=False,
                     approach: str|None=None) -> dict:
    import yaml
    registry=existing(root); m=registry.get(aid)
    need(registry.readiness(aid).ready,'Candidate artifact is not file-ready')
    cfg=load_pipeline_config(base or root/'config/production.yaml',registry).snapshot()
    cfg['pipeline']['name']='candidate_'+aid.replace('/','_')
    if m.stage==1:
        need(not single,'--single applies only to Stage 2')
        cfg['stage1']['artifact']=aid
        if approach is not None: cfg['stage1']['approach']=approach
    else:
        need(approach is None,'--approach applies only to Stage 1')
        row={'adapter':m.adapter,'artifact':aid}
        if single:
            cfg['stage2']={'mode':'single','methods':[row]};cfg['stage1']['enabled']=False
        else:
            need(any(x['adapter']==m.adapter for x in cfg['stage2']['methods']),'Adapter not selected in base config; use --single')
            cfg['stage2']['methods']=[row if x['adapter']==m.adapter else x for x in cfg['stage2']['methods']]
    text=yaml.safe_dump(cfg,sort_keys=False)
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'candidate.yaml'; write_new(path,text); load_pipeline_config(path,registry)
    write_new(output,text)
    return {'artifact_id':aid,'config':str(output),'activated':False,'runtime_validated':False}
