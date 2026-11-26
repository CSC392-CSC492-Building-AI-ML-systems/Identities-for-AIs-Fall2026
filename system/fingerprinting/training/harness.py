"""Build a review-only six-probe Harness reference bundle (no fitted weights).

The original v1 runtime is immutable. v2 snapshots the three upstream modules
with explicit, checked transformations and a narrow API entry point. It uses only
training personas and sample indices 0/1; validation is coverage audit only.
"""
from __future__ import annotations
import ast
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
import yaml
from ..model_catalog import ModelCatalog
from ..onboarding import artifacts as a, datasets as d
from .random_forest import load_traces
from .orchestrator import UnchangedCandidate

ROOT=Path(__file__).resolve().parents[2]
PROBES=['LM-01','LM-05','LM-06','I1','I2','V1-15']
ABI='catalog_reference_v2'
SAMPLES=(0,1)
# The catalog predates product-line metadata for these three entries. Keep the
# original Harness distinction between product line and canonical broad family.
LINES={'claude-haiku-5.5':'Claude Haiku','gpt-6.1-terra':'GPT Terra','gpt-6-luna':'GPT Luna'}

def parameters(raw):
    if set(raw)-{'judge_provider','judge_model'}: raise ValueError('Unknown Harness builder parameter')
    p={'judge_provider':'google','judge_model':'gemini-3.8-flash',**raw}
    if p['judge_provider'] not in ('google','openai','mock'): raise ValueError('Choose google, openai or mock; Anthropic transport not validated')
    if not isinstance(p['judge_model'],str) or not p['judge_model'].strip(): raise ValueError('Specify judge model')
    return p

def replace_once(text,old,new):
    if text.count(old)!=1: raise ValueError('Upstream source contract changed; review Harness migration')
    return text.replace(old,new,1)

def replace_literal(text,name,value):
    nodes=[n for n in ast.parse(text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
    if len(nodes)!=1: raise ValueError('Upstream assignment missing: '+name)
    n=nodes[0]; ast.literal_eval(n.value)
    lines=text.splitlines(keepends=True)
    return ''.join(lines[:n.lineno-1])+name+' = '+repr(value)+'\n'+''.join(lines[n.end_lineno:])

def model_maps(catalog,labels):
    models={}; developers={}
    for key in labels:
        m=catalog.get(key); line=m.product_line or LINES.get(key) or m.family_id.capitalize()
        if line in developers and developers[line]!=m.developer: raise ValueError('Ambiguous product line')
        models[key]=(line,m.display_name); developers[line]=m.developer
    if len({v[1] for v in models.values()})!=len(models): raise ValueError('Duplicate judge display labels')
    return models,developers

def prepare_references(train_path,val_path,info,catalog):
    if info.get('split_algorithm')!=d.PANEL_ALGORITHM or set(info.get('probe_pool') or [])!=set(PROBES) or info.get('prompt_set_version')!='fingerprint_v0':
        raise ValueError('Harness requires the original six-probe fingerprint_v0 panel')
    train=load_traces(train_path,PROBES,'fingerprint_v0'); val=load_traces(val_path,PROBES,'fingerprint_v0')
    train_personas={t['persona_id'] for t in train}; val_personas={t['persona_id'] for t in val}
    if train_personas & val_personas: raise ValueError('Persona leakage')
    labels=sorted({t['model_id'] for t in train})
    if len(labels)<2 or set(labels)!={t['model_id'] for t in val}: raise ValueError('Training and validation classes differ')
    maps,devs=model_maps(catalog,labels)
    ids={rid for t in train for rid in t['record_ids'].values()}
    if ids & {rid for t in val for rid in t['record_ids'].values()}: raise ValueError('Record overlap')
    rows=defaultdict(list); counts=Counter(); blanks=Counter(); ref_ids=set()
    for _,r,_ in d.read_rows(train_path):
        if r['sample_index'] not in SAMPLES: continue
        k=r['model_key']; p=r['prompt_id']; rows[k].append(r); counts[k,p]+=1
        blanks[k,p]+=not bool((r['response_text'] or '').strip()); ref_ids.add(r['record_id'])
    if any(counts[k,p]<4 for k in labels for p in PROBES): raise ValueError('Each model/probe requires at least four reference responses')
    for k in rows: rows[k].sort(key=lambda r:(r['persona_id'],r['sample_index'],r['prompt_id'],r['record_id']))
    report={'status':'reference_coverage_only','judge_called':False,'test_used':False,'validation_used_for_references':False,
        'train_personas':sorted(train_personas),'validation_personas':sorted(val_personas),'training_traces':len(train),'validation_traces':len(val),
        'reference_records':len(ref_ids),'blank_reference_records':sum(blanks.values()),'excluded_training_sample2_records':len(ids-ref_ids),
        'models':{k:{p:{'references':counts[k,p],'blank':blanks[k,p]} for p in PROBES} for k in labels}}
    return dict(rows),maps,devs,report

API_SOURCE='''"""Narrow v2 identification entry; backend owns deployment history and cards."""
from types import SimpleNamespace
import check_chatbot
from probe_identify import DEFAULT_PROBES

def identify(answers, domain=None, deployment=None, judge_provider="google", judge_model="gemini-3.8-flash", handoff_below=0.7):
    if deployment is not None: raise ValueError("Use backend deployment history")
    if not isinstance(answers,dict) or set(answers)!=set(DEFAULT_PROBES) or any(not isinstance(a,str) for a in answers.values()):
        raise ValueError("All six string answers required; blanks are valid observations")
    session={p:answers[p] if answers[p].strip() else "" for p in DEFAULT_PROBES}
    args=SimpleNamespace(judge_provider=judge_provider,judge_model=judge_model,handoff_below=handoff_below)
    return check_chatbot.identify_answers(session,args)
'''

def sources(base,maps,devs):
    identify=(base/'agent/identify.py').read_text(encoding='utf-8')
    identify=replace_literal(identify,'MODELS',maps);identify=replace_literal(identify,'DEVELOPER',devs)
    identify=replace_once(identify,'if not r.get("error") and r.get("response_text"):', 'if r.get("error") is None and (r.get("response_text") is None or isinstance(r.get("response_text"), str)):\n                        r["response_text"] = (r.get("response_text") or "") if (r.get("response_text") or "").strip() else ""')
    # Limit to the supported, explicit judge transports; do not invent a new API.
    probe=(base/'agent/probe_identify.py').read_text(encoding='utf-8')
    probe=replace_once(probe,'parts.append(f"refuses {100 * refuse // n}%")','parts.append(f"refuses {100 * refuse // n}%")\n    parts.append(f"blank {100 * sum(not a.strip() for a in answers) // n}%")')
    probe=replace_once(probe,'median = statistics.median(len(r) for r in refs)\n        if len(answer) > length_factor * median or len(answer) < median / length_factor:', 'blank_share = sum(not r.strip() for r in refs) / len(refs)\n        if (not answer.strip() and blank_share < rare) or (answer.strip() and blank_share > 1 - rare):\n            why.append("blank")\n        nonblank = [len(r) for r in refs if r.strip()]\n        median = statistics.median(nonblank) if nonblank else None\n        if answer.strip() and median is not None and (len(answer) > length_factor * median or len(answer) < median / length_factor):')
    probe=replace_once(probe,'example = answers[0][:EXAMPLE_CHARS].replace("\\n", " ") if answers else "(none)"','example = (answers[0][:EXAMPLE_CHARS].replace("\\n", " ") or "[EMPTY_RESPONSE]") if answers else "(none)"')
    # Use repr for unambiguous blank rendering without changing original text.
    probe=replace_once(probe,'parts.append(f"CHATBOT\'S ANSWER:\\n{session[pid][:ANSWER_CHARS]}\\n")','answer = session[pid][:ANSWER_CHARS] or "[EMPTY_RESPONSE]"\n        parts.append(f"CHATBOT\'S ANSWER:\\n{answer}\\n")')
    check=(base/'agent/check_chatbot.py').read_text(encoding='utf-8')
    # A version label is the authoritative *candidate*; normalize the associated
    # product line to its catalog entry, never rely on judge family text.
    check=replace_once(check,'judge_key, sibling_rule = sibling_check(session, judge_key, known, recs)','if judge_key:\n        pred = dict(pred, family=MODELS[judge_key][0], version=MODELS[judge_key][1])\n    judge_key, sibling_rule = sibling_check(session, judge_key, known, recs)')
    result={'agent/identify.py':identify,'agent/probe_identify.py':probe,'agent/check_chatbot.py':check,'agent/identify_api.py':API_SOURCE}
    for k,v in result.items(): compile(v,k,'exec')
    return result

class HarnessTrainer:
    def supports(self,info): return info.get('split_algorithm')==d.PANEL_ALGORITHM and set(info.get('probe_pool') or [])==set(PROBES) and info.get('prompt_set_version')=='fingerprint_v0'
    def check_parameters(self,raw): parameters(raw)
    def run(self,ctx):
        p=parameters(ctx.parameters);root=getattr(ctx,'system_root',None) or ROOT
        registry=a.existing(root); base=registry.get('harness/v1')
        if not registry.readiness('harness/v1').ready: raise ValueError('Pinned Harness v1 source bundle failed integrity check')
        rows,maps,devs,report=prepare_references(ctx.train_jsonl,ctx.validation_jsonl,{'split_algorithm':ctx.split_algorithm,'probe_pool':ctx.probe_pool,'prompt_set_version':ctx.prompt_set_version},registry.catalog)
        payload=sources(base.directory,maps,devs)
        promptfile=base.directory/'collector/prompts/fingerprinting_prompts.yaml'
        promptmap={r['id']:r['text'] for r in yaml.safe_load(promptfile.read_text(encoding='utf-8'))['prompts']}
        payload['collector/prompts/fingerprinting_prompts.yaml']=yaml.safe_dump({'prompts':[{'id':q,'text':promptmap[q]} for q in PROBES]},sort_keys=False,allow_unicode=True)
        for key,rs in rows.items(): payload[f'collector/data/raw/{key}/fingerprint_v0.jsonl']=''.join(json.dumps(r,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n' for r in rs)
        options={'reference_abi':ABI,'probe_ids':PROBES,**p,'handoff_below':0.7,'timeout_seconds':240,'min_probes':6,'acceptance_policy':'review_only','reference_split':'sample_index in {0,1} only','worker_entry':'agent/identify_api.py'}
        digest=hashlib.sha256(json.dumps({'payload':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sorted(payload.items())},'options':options},sort_keys=True).encode()).hexdigest()
        unchanged=[aid for aid in registry.artifact_ids if aid.startswith('harness/') and registry.get(aid).provenance.get('reference_build_sha256')==digest and registry.readiness(aid).ready]
        report.update(reference_build_sha256=digest,matching_registered_artifacts=unchanged)
        if unchanged: raise UnchangedCandidate(unchanged)
        out=ctx.output_dir
        for path,value in payload.items(): a.write_new(out/path,value)
        a.write_new(out/'reference_report.json',a.json_text(report))
        names=sorted([*payload,'reference_report.json'])
        a.write_new(out/'manifest.json',a.json_text({'schema_version':'1.0','artifact_id':ctx.artifact_id,'adapter':'harness','stage':2,'kind':'agentic_identifier','supported_models':sorted(maps),'required_files':[{'path':f,'sha256':a.digest(out/f)} for f in names],'options':options,
        'provenance':{'source':'Pinned Harness v1, catalog-driven six-probe reference builder','source_artifact':'harness/v1','source_manifest_sha256':base.manifest_sha256,'training_code_revision':'sha256:'+a.digest(Path(__file__)),'runtime_dependencies':{'python':sys.version.split()[0],'PyYAML':yaml.__version__},'training_dataset_id':ctx.dataset_id,'split_id':ctx.split_id,'dataset_manifest_sha256':ctx.dataset_manifest_sha256,'split_manifest_sha256':ctx.split_manifest_sha256,'eligibility_policy':ctx.eligibility_policy,'reference_build_sha256':digest,'test_used':False,'judge_validated':False}}))
