"""Offline onboarding of target identities, not fingerprint classifier versions.

The catalog remains authoritative for labels; collector routing and research cards
remain in the team's sibling directories. No external requests or model training.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
import yaml
from .artifacts import need, read_json, json_text, safe_rel
from ..model_catalog import ModelCatalog
from ..registry import ArtifactRegistry

DOMAINS = ('compliance', 'governance', 'evaluation', 'risk')
PROVIDERS = ('ollama', 'openai', 'anthropic', 'google')
REQUIRED = {'model_id','family_id','family_name','developer','display_name','provider','provider_model_id','access','identity_source','researched_by'}
OPTIONAL = {'product_line','delay_seconds'}

class UniqueLoader(yaml.SafeLoader):
    pass

def unique_mapping(loader, node):
    loader.flatten_mapping(node)
    result = {}
    for k,v in node.value:
        key = loader.construct_object(k)
        need(key not in result, f'Duplicate YAML key: {key!r}')
        result[key] = loader.construct_object(v)
    return result
UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)

def yaml_doc(path):
    data = yaml.load(path.read_text(encoding='utf-8'), Loader=UniqueLoader)
    need(isinstance(data,dict), f'{path.name}: expected YAML mapping')
    return data

def identifier(s):
    need(isinstance(s,str) and re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,99}',s) is not None, 'Use a lowercase canonical ID (letters, digits, dots, hyphens, underscores)')
    safe_rel(s)
    return s

def slug(s):
    return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')

def spec_load(path):
    s = read_json(path)
    need(REQUIRED <= set(s) <= REQUIRED|OPTIONAL, 'Missing or unexpected submission fields')
    for k in REQUIRED | (set(s)&{'product_line'}):
        v=s[k]; need(isinstance(v,str) and v.strip()==v and bool(v) and len(v)<=512 and not any(ord(c)<32 for c in v),f'Invalid {k}')
    identifier(s['model_id']);identifier(s['family_id'])
    need(slug(s['family_name'])==s['family_id'], 'family_name must normalize to family_id')
    need(s['provider'] in PROVIDERS, 'Provider requires an existing collector transport; add new transports separately')
    need(s['access'] in ('open','closed'), 'access must be open or closed')
    need(not s['provider_model_id'].lower().startswith('todo'), 'Supply an exact provider model ID, not TODO')
    need(s['model_id']!='mock-model', 'Reserved mock model ID')
    u=urlparse(s['identity_source']);need(u.scheme=='https' and bool(u.hostname) and not u.username and not u.password,'Provide an HTTPS identity source (not fetched or verified by the tool)')
    if 'delay_seconds' in s: need(type(s['delay_seconds']) is int and 0<=s['delay_seconds']<=3600,'Invalid delay_seconds')
    return s

def paths(root):
    root=Path(root).resolve(); repo=root.parent
    return root/'catalog/models.json', root/'collector/models.yaml', repo/'cards'

def collector(path):
    doc=yaml_doc(path); rows=doc.get('models')
    need(isinstance(rows,list) and all(isinstance(x,dict) and isinstance(x.get('model_key'),str) for x in rows),'Invalid collector model list')
    result={x['model_key']:x for x in rows};need(len(result)==len(rows),'Duplicate collector model keys')
    return doc,result

def entry(s):
    return {**{k:s[k] for k in ('family_id','developer','display_name','provider','provider_model_id')},
            **({'product_line':s['product_line']} if 'product_line' in s else {}),
            **{k:s[k] for k in ('family_name','access','identity_source')}}

def card_headers(cards,key):
    out={}
    for d in DOMAINS:
        p=cards/'data'/d/(key+'.yaml')
        if p.exists(): out[d]=yaml_doc(p)
    return out

def plan(root,s,allow_new_family=False):
    cp,mp,cards=paths(root); cat=ModelCatalog.from_file(cp); raw=read_json(cp); doc,rows=collector(mp)
    key=s['model_id'];family=s['family_id'];new_family=not any(m['family_id']==family for m in raw['models'].values())
    need(not new_family or allow_new_family,'New family requires --allow-new-family')
    for k,m in raw['models'].items():
        if m['family_id']==family:
            need(m['developer']==s['developer'], 'Family developer differs from existing catalog members; review manually')
            need(not m.get('family_name') or m['family_name'].casefold()==s['family_name'].casefold(),'Family display name conflicts with catalog')
            for c in card_headers(cards,k).values():
                need(isinstance(c.get('family'),str) and c['family'].casefold()==s['family_name'].casefold(),'Family name conflicts with authoritative card headers')
        if k!=key:
            need(m['display_name'].casefold()!=s['display_name'].casefold(),'Duplicate catalog display name (Harness judge label)')
            need((m.get('provider'),m.get('provider_model_id'))!=(s['provider'],s['provider_model_id']),'Provider route already belongs to another canonical identity')
            if s.get('product_line') and m.get('product_line')==s['product_line']:
                need(m['developer']==s['developer'],'Product line belongs to a different developer')
    if key in raw['models']:
        prior=raw['models'][key]
        for k,v in entry(s).items():
            if k in prior: need(prior[k]==v,f'Existing catalog identity differs in {k}; no automatic rewrite')
        for k in ('family_id','developer','display_name','provider','provider_model_id','product_line'):
            need(prior.get(k)==entry(s).get(k),f'Existing catalog identity differs in {k}; no automatic rewrite')
    for k,r in rows.items():
        if k==key: need((r.get('provider'),r.get('model_id'))==(s['provider'],s['provider_model_id']),'Existing collector route differs; reconcile manually')
        else: need((r.get('provider'),r.get('model_id'))!=(s['provider'],s['provider_model_id']),'Collector route already assigned to another identity')
    for c in card_headers(cards,key).values():
        need(c.get('family','').casefold()==s['family_name'].casefold() and c.get('access')==s['access'],'Existing card metadata differs; review manually')
    need((cards/'new_model.py').is_file() and (cards/'cardlib.py').is_file() and (cards/'check_cards.py').is_file(),'Authoritative sibling cards/ scripts required')
    for d in DOMAINS: need((cards/'fields'/f'{d}.yaml').is_file(),'Missing authoritative card field definitions')
    row={'model_key':key,'provider':s['provider'],'model_id':s['provider_model_id'],'enabled':False}
    if 'delay_seconds' in s: row['delay_seconds']=s['delay_seconds']
    return {'model_id':key,'family_id':family,'new_family':new_family,'catalog_action':'keep' if cat.has(key) else 'add',
            'collector_action':'keep' if key in rows else 'add_disabled','collector_entry':rows.get(key,row),
            'missing_card_domains':[d for d in DOMAINS if d not in card_headers(cards,key)],
            'classifier_artifacts_changed':False,'automatic_activation':False,'identity_source_verified':False}

@contextmanager
def lock(root):
    p=Path(root)/'.local/model_onboarding.lock';p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f: f.write(str(os.getpid()))
    try: yield
    finally: p.unlink()

def commit(changes):
    """Preflight and replace per file, best-effort rollback on ordinary failures.
    Not a multi-file transaction across crashes; use a clean Git branch.
    """
    temps={};done=[]
    try:
        for p,(old,new) in changes.items():
            need(not p.is_symlink() and (p.read_bytes() if p.exists() else None)==old,f'File changed since planning: {p}')
            p.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as f:
                temps[p]=Path(f.name);f.write(new);f.flush();os.fsync(f.fileno())
        for p,(old,new) in changes.items():
            need((p.read_bytes() if p.exists() else None)==old,f'File changed during publication: {p}')
            os.replace(temps[p],p);done.append(p)
    except Exception:
        for p in reversed(done):
            old,new=changes[p]
            if p.exists() and p.read_bytes()==new:
                if old is None: p.unlink()
                else: p.write_bytes(old)
        raise
    finally:
        for t in temps.values(): t.unlink(missing_ok=True)

def register(root,s,allow_new_family=False):
    with lock(root):
        cp,mp,_=paths(root); before_c=cp.read_bytes();before_m=mp.read_bytes();p=plan(root,s,allow_new_family); changes={}
        if p['catalog_action']=='add':
            doc=read_json(cp);doc['models'][s['model_id']]=entry(s);new=json_text(doc).encode();changes[cp]=(before_c,new)
        if p['collector_action']=='add_disabled':
            doc,_=collector(mp);need(set(doc)=={'models'},'Collector YAML contains extra top-level fields; review manually before appending')
            row=p['collector_entry']; doc['models'].append(row)
            # Preserve comments and existing formatting; verify the appended YAML parses exactly as expected.
            addition='\n  - '+yaml.safe_dump(row,default_flow_style=True,sort_keys=False,width=10000,allow_unicode=True).strip()+'\n'
            new=before_m.decode('utf-8').rstrip('\r\n')+'\n'+addition
            need(yaml.load(new,Loader=UniqueLoader)==doc,'Cannot safely append to collector YAML; use manual edit')
            changes[mp]=(before_m,new.encode('utf-8'))
        commit(changes)
        return {**p,'status':'registered' if changes else 'unchanged','changed_files':[str(x.relative_to(Path(root).resolve().parent)) for x in changes]}

# Run the existing, trusted sibling card scripts in a fresh process (no module-path
# collisions with pinned Harness copies). This is a developer CLI, not upload code.
CARD_HELPER='''import json,sys,argparse
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import cardlib,new_model,check_cards
job=json.loads(sys.stdin.read())
if job['action']=='draft':
    args=argparse.Namespace(**job['args']);print(json.dumps({d:new_model.blank_card(d,args) for d in job['domains']}))
else:
    models=cardlib.collector_models();lics=cardlib.licences();result={}
    for d,path in job['paths'].items():
        p=Path(path);errors,todos=check_cards.check_file(d,p,models,lics)
        if d=='compliance' and p.exists():
            c=cardlib.load_yaml(p);lic=lics.get(c.get('licence_id'),{})
            if not lic.get('official_url') or cardlib.is_todo(lic.get('official_url')): errors.append('Missing authoritative licence URL')
        result[d]={'errors':errors,'todos':todos}
    print(json.dumps(result))
'''
def card_call(cards,job):
    p=subprocess.run([sys.executable,'-B','-c',CARD_HELPER,str(cards)],input=json.dumps(job),text=True,encoding='utf-8',capture_output=True,check=False,timeout=30,cwd=cards)
    need(p.returncode==0,'Authoritative card tool failed: '+p.stderr[-1500:]);return json.loads(p.stdout)

def require_registered(root,s):
    p=plan(root,s,False);need(p['catalog_action']==p['collector_action']=='keep','Register identity and collector route first');return p

def draft(root,s):
    with lock(root):
        p=require_registered(root,s);_,_,cards=paths(root); key=s['model_id'];out=Path(root)/'.local/model_onboarding'/key
        missing=p['missing_card_domains'];contents=card_call(cards,{'action':'draft','args':{'model_key':key,'name':s['display_name'],'family':s['family_name'],'access':s['access'],'by':s['researched_by']},'domains':missing})
        changes={}
        for d,txt in contents.items():
            data=yaml.load(txt,Loader=UniqueLoader); need(data['model_key']==key and data['name']==s['display_name'] and data['family']==s['family_name'] and data['researched_by']==s['researched_by'],'Card generator cannot safely represent these header values')
            f=out/d/(key+'.yaml')
            if not f.exists(): changes[f]=(None,txt.encode('utf-8'))
        commit(changes)
        return {'model_id':key,'draft_directory':str(out),'created_domains':[p.parent.name for p in changes],'existing_authoritative_domains':[d for d in DOMAINS if d not in missing],'status':'draft_only','published':False}

def publish_cards(root,s):
    with lock(root):
        p=require_registered(root,s);_,_,cards=paths(root);key=s['model_id'];out=Path(root)/'.local/model_onboarding'/key
        files={};changes={};snapshots={}
        for d in DOMAINS:
            target=cards/'data'/d/(key+'.yaml');source=target if target.exists() else out/d/(key+'.yaml');need(source.is_file(),f'Missing {d} research card')
            c=yaml_doc(source);need(c.get('family')==s['family_name'] and c.get('access')==s['access'] and c.get('model_key')==key,f'{d}: inconsistent card header')
            files[d]=str(source);snapshots[source]=source.read_bytes()
            if source!=target: changes[target]=(None,snapshots[source])
        checked=card_call(cards,{'action':'check','paths':files});need(all(not r['errors'] and not r['todos'] for r in checked.values()),'Cards are incomplete or invalid: '+json.dumps(checked))
        # No automatic licence assignment or claim of factual/legal verification.
        need(all(p.read_bytes()==b for p,b in snapshots.items()),'Research cards changed during validation')
        commit(changes);return {'model_id':key,'status':'published' if changes else 'unchanged','domains':list(DOMAINS),'published_domains':[p.parent.name for p in changes],'research_verified_by_tool':False}

def status(root):
    cp,mp,cards=paths(root);catalog=ModelCatalog.from_file(cp);_,rows=collector(mp);registry=ArtifactRegistry(root,catalog)
    manifests=[registry.get(x) for x in registry.artifact_ids];result={};families={}
    for key in sorted(catalog.model_ids):
        m=catalog.get(key);r=rows.get(key);headers=card_headers(cards,key);files={d:str(cards/'data'/d/(key+'.yaml')) for d in headers}
        checks=card_call(cards,{'action':'check','paths':files}) if files else {};domain_status={d:('missing' if d not in checks else 'invalid' if checks[d]['errors'] else 'draft' if checks[d]['todos'] else 'complete') for d in DOMAINS}
        route='missing' if not r else 'match' if (r.get('provider'),r.get('model_id'))==(m.provider,m.provider_model_id) else 'mismatch'
        result[key]={'family_id':m.family_id,'collector_route':route,'collector_enabled':bool(r and r.get('enabled',True)), 'cards':domain_status,'card_checks':checks,'declared_stage2_artifacts':[a.artifact_id for a in manifests if a.stage==2 and a.supports(key)]}
        families.setdefault(m.family_id,[]).append(key)
    return {'summary':{'model_count':len(result),'family_count':len(families),'collector_routes':{s:sum(v['collector_route']==s for v in result.values()) for s in ('match','missing','mismatch')},'card_domains':{s:sum(x==s for v in result.values() for x in v['cards'].values()) for s in ('complete','draft','invalid','missing')}},'models':result,'families':families,'collector_only_models':sorted(set(rows)-catalog.model_ids-{'mock-model'}),'note':'Declared support is not validated accuracy, artifact readiness, or activation. Card checks are structural, not evidence verification.'}
