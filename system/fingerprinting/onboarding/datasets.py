"""Offline collector dataset ingestion; raw snapshots are never edited in place."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from ..model_catalog import ModelCatalog
from .artifacts import digest, read_json, write_new

PARTITIONS = ('train', 'calibration', 'validation', 'test')
DEFAULT_WEIGHTS = (60, 10, 15, 15)
CURRENT_ELIGIBILITY = 'include_blank_without_error_v2'
LEGACY_ELIGIBILITY = 'exclude_blank_without_error_v1'
ELIGIBILITY_POLICIES = (CURRENT_ELIGIBILITY, LEGACY_ELIGIBILITY)
ALGORITHM = 'sha256_prompt_groups_coverage_search_v2'
PANEL_ALGORITHM = 'fixed_probe_persona_holdout_v1'
COVERAGE_ATTEMPTS = 128
COMPONENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z')
MAX_BYTES = 1024**3
MAX_LINE = 8 * 1024**2


class DatasetError(ValueError):
    """Invalid dataset, manifest or split request."""


def require(condition, message):
    if not condition:
        raise DatasetError(message)


def component(value):
    return (isinstance(value, str) and bool(COMPONENT.fullmatch(value))
            and not value.endswith('.') and value.split('.')[0].upper() not in
            {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
             *(f'LPT{i}' for i in range(1, 10))})


def json_text(obj):
    return json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False) + '\n'


def raw_path(name):
    parts = name.split('/')
    require(len(parts) == 3 and parts[0] == 'raw' and component(parts[1])
            and parts[2].endswith('.jsonl') and component(parts[2][:-6]),
            'Expected raw/<model_id>/<prompt_set_version>.jsonl')
    return PurePosixPath(name)


def raw_files(raw):
    require(raw.is_dir() and not raw.is_symlink(), 'Missing or symlinked raw directory')
    paths = []
    total = 0
    folded = set()
    for p in sorted(raw.rglob('*')):
        require(not p.is_symlink(), 'Symlinks are not supported in raw collections')
        if p.is_dir():
            require(len(p.relative_to(raw).parts) == 1 and component(p.name), 'Unexpected raw directory')
            continue
        rel = raw_path('raw/' + p.relative_to(raw).as_posix())
        require(p.is_file(), 'Only regular JSONL files are supported')
        require(str(rel).casefold() not in folded, 'Case-insensitive path collision')
        folded.add(str(rel).casefold())
        total += p.stat().st_size
        require(total <= MAX_BYTES, 'Dataset exceeds 1 GiB uncompressed limit')
        paths.append((str(rel), p))
    require(paths, 'No raw JSONL files found')
    return paths


@contextmanager
def open_source(source):
    """Read a raw directory, snapshot directory or collector ZIP; never extract arbitrary paths."""
    source = Path(source)
    require(not source.is_symlink(), 'Source must not be a symlink')
    if source.is_dir():
        raw = source / 'raw' if (source / 'raw').exists() else source
        yield raw
        return
    require(source.is_file() and zipfile.is_zipfile(source), 'Expected raw directory or collector ZIP')
    with tempfile.TemporaryDirectory(prefix='dataset-source-') as temp, zipfile.ZipFile(source) as archive:
        base = Path(temp)
        seen = set()
        total = 0
        for info in archive.infolist():
            name = info.filename
            mode = info.external_attr >> 16
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), 'Unsupported ZIP member type')
            if info.is_dir():
                parts = name.rstrip('/').split('/')
                require(parts == ['raw'] or (len(parts) == 2 and parts[0] == 'raw' and component(parts[1])), 'Unexpected ZIP directory')
                continue
            rel = raw_path(name)
            require(name.casefold() not in seen, 'Duplicate ZIP file or case collision')
            seen.add(name.casefold())
            total += info.file_size
            require(total <= MAX_BYTES, 'ZIP exceeds 1 GiB uncompressed limit')
            dst = base.joinpath(*rel.parts)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, dst.open('xb') as out:
                shutil.copyfileobj(src, out)
        yield base / 'raw'


def strict_object(line):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise DatasetError('Non-finite JSON constant')
    obj = json.loads(line.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    require(isinstance(obj, dict), 'JSONL record must be an object')
    return obj


def read_rows(path):
    with path.open('rb') as stream:
        line_no = 0
        while line := stream.readline(MAX_LINE + 1):
            line_no += 1
            try:
                require(len(line) <= MAX_LINE, 'JSONL line exceeds 8 MiB')
                require(bool(line.strip()), 'Blank JSONL line')
                row = strict_object(line)
            except (ValueError, UnicodeError) as exc:
                raise DatasetError(f'{path.name}:{line_no}: malformed record ({type(exc).__name__})') from None
            yield line_no, row, line


def scan(root, raw, *, eligibility_policy=CURRENT_ELIGIBILITY):
    require(eligibility_policy in ELIGIBILITY_POLICIES, 'Unknown eligibility policy')
    catalog_path = root / 'catalog/models.json'
    catalog = ModelCatalog.from_file(catalog_path)
    files, records, ids = [], [], set()
    totals, per_model, per_set = Counter(), defaultdict(Counter), defaultdict(Counter)
    by_model_prompts, response_keys = defaultdict(set), set()
    repeated = 0
    for rel, path in raw_files(raw):
        model, version = PurePosixPath(rel).parts[1:]
        version = version[:-6]
        require(catalog.has(model), f'Unknown canonical model directory: {model}')
        family = catalog.get(model).family_id
        counts = Counter()
        for number, row, _ in read_rows(path):
            loc = f'{rel}:{number}'
            for field in ('record_id', 'model_key', 'prompt_id', 'prompt_set_version', 'prompt_group', 'persona_id'):
                require(isinstance(row.get(field), str) and bool(row[field].strip()), f'{loc}: missing/invalid {field}')
            require(row['model_key'] == model and row['prompt_set_version'] == version, f'{loc}: model or prompt-set mismatch')
            require('response_text' in row and (row['response_text'] is None or isinstance(row['response_text'], str)), f'{loc}: invalid response_text')
            require('error' in row and (row['error'] is None or isinstance(row['error'], str)), f'{loc}: invalid error')
            require(row.get('reasoning_text') is None or isinstance(row['reasoning_text'], str), f'{loc}: invalid reasoning_text')
            require(row.get('refused') is None or type(row['refused']) is bool, f'{loc}: invalid refused flag')
            rid = row['record_id']
            require(rid not in ids, f'{loc}: duplicate record_id')
            ids.add(rid)
            text = row['response_text'] or ''
            quality = ('recorded_error' if row['error'] is not None else
                       'blank_response' if not text.strip() else 'eligible')
            reason = quality if quality == 'recorded_error' or (quality == 'blank_response' and eligibility_policy == LEGACY_ELIGIBILITY) else None
            counts[quality] += 1
            totals[quality] += 1
            per_model[model][quality] += 1
            per_set[version][quality] += 1
            if row.get('reasoning_text') and row['reasoning_text'].strip():
                counts['nonempty_reasoning'] += 1
                totals['nonempty_reasoning'] += 1
                if quality == 'blank_response':
                    totals['blank_with_reasoning'] += 1
            if row.get('refused') is True:
                totals['refused'] += 1
            if not reason:
                by_model_prompts[model].add(row['prompt_id'])
                key = (model, row['prompt_id'], row['persona_id'], hashlib.sha256(text.encode('utf-8', errors='surrogatepass')).hexdigest())
                repeated += key in response_keys
                response_keys.add(key)
            records.append({'record_id':rid, 'path':rel, 'line':number, 'model_id':model,
                            'family_id':family, 'prompt_id':row['prompt_id'], 'prompt_set_version':version,
                            'prompt_group':row['prompt_group'], 'exclusion':reason})
        n = sum(counts[k] for k in ('eligible','recorded_error','blank_response'))
        require(n > 0, f'{rel}: empty JSONL file')
        files.append({'path':rel,'sha256':digest(path),'bytes':path.stat().st_size,'model_id':model,
                      'family_id':family,'prompt_set_version':version,'records':n,
                      'nonempty_without_error':counts['eligible'],'recorded_errors':counts['recorded_error'],
                      'blank_without_error':counts['blank_response']})
    summary = {'records':len(records),'eligible':sum(not r['exclusion'] for r in records),'recorded_errors':totals['recorded_error'],
               'blank_without_error':totals['blank_response'],'nonempty_reasoning':totals['nonempty_reasoning'],
               'blank_with_reasoning':totals['blank_with_reasoning'],'refused':totals['refused'],
               'repeated_exact_responses_same_model_prompt_persona':repeated,'duplicate_record_ids':0,
               'model_count':len(per_model),'family_count':len({r['family_id'] for r in records}),
               'distinct_prompt_ids':len({r['prompt_id'] for r in records}),
               'by_model':{m:{**dict(c),'nonempty_without_error':c['eligible'],'eligible':c['eligible']+(c['blank_response'] if eligibility_policy==CURRENT_ELIGIBILITY else 0),'eligible_prompt_ids':len(by_model_prompts[m])} for m,c in per_model.items()},
               'by_prompt_set':{s:{**dict(c),'nonempty_without_error':c['eligible'],'eligible':c['eligible']+(c['blank_response'] if eligibility_policy==CURRENT_ELIGIBILITY else 0)} for s,c in per_set.items()}}
    return {'schema_version':'1.0','status':'raw_unreviewed','catalog_sha256':digest(catalog_path),
            'files':files,'summary':summary,'eligibility_policy':eligibility_policy}, records


def validate(root, source):
    with open_source(source) as raw:
        report, _ = scan(root, raw)
    return report


def dataset_dir(root, dataset_id):
    parts = dataset_id.split('/')
    require(len(parts) == 2 and parts[0] == 'collector_raw' and component(parts[1]),
            'Dataset ID must be collector_raw/<version>')
    path = root / 'datasets' / parts[0] / parts[1]
    require(not any(p.is_symlink() for p in (root/'datasets', path.parent, path)), 'Symlinked dataset path')
    return path


@contextmanager
def publish_new(destination):
    """Local atomic directory publication; no overwrite of prior version."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / ('.' + destination.name + '.lock')
    try:
        lock.touch(exist_ok=False)
    except FileExistsError:
        raise DatasetError('Another publication is active (or stale local lock)') from None
    try:
        require(not destination.exists() and not destination.is_symlink(), 'Version already exists; choose a new version')
        with tempfile.TemporaryDirectory(prefix='.dataset-staging-', dir=destination.parent) as tmp:
            stage = Path(tmp) / 'publish'
            stage.mkdir()
            yield stage
            require(not destination.exists() and not destination.is_symlink(), 'Version already exists')
            stage.rename(destination)
    finally:
        lock.unlink()


def register(root, source, version, *, source_note):
    require(component(version), 'Invalid dataset version')
    require(isinstance(source_note,str) and bool(source_note.strip()), 'Supply a source note')
    dataset_id = 'collector_raw/' + version
    destination = dataset_dir(root, dataset_id)
    with open_source(source) as raw, publish_new(destination) as stage:
        for rel, p in raw_files(raw):
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
        report, _ = scan(root, stage / 'raw')
        report.update(dataset_id=dataset_id, source_note=source_note, privacy_review='pending',
                      license_review='pending', source_archive_sha256=digest(Path(source)) if Path(source).is_file() else None)
        write_new(stage/'manifest.json', json_text(report))
        write_new(stage/'README.md', f'# Dataset {dataset_id}\n\nRaw unreviewed collector snapshot. See manifest.json for integrity and quality counts.\nReview privacy and licenses before sharing. No model has been trained or activated.\n')
    return {'dataset_id':dataset_id,'manifest_sha256':digest(destination/'manifest.json'), 'summary':report['summary']}


def load_snapshot(root, dataset_id, *, eligibility_policy=CURRENT_ELIGIBILITY):
    base = dataset_dir(root, dataset_id)
    manifest_path = base / 'manifest.json'
    require(manifest_path.is_file() and not manifest_path.is_symlink(), 'Dataset manifest not found')
    manifest = read_json(manifest_path)
    require(manifest.get('dataset_id') == dataset_id and manifest.get('schema_version') == '1.0', 'Dataset manifest identity/version mismatch')
    report, rows = scan(root, base/'raw', eligibility_policy=eligibility_policy)
    def inventory(entries):
        require(isinstance(entries,list), 'Invalid manifest file inventory')
        result = {e['path']:(e['sha256'], e['bytes']) for e in entries}
        require(len(result)==len(entries), 'Duplicate manifest path')
        return result
    require(inventory(manifest.get('files')) == inventory(report['files']), 'Raw snapshot differs from registered manifest')
    return base, digest(manifest_path), report, rows


def overlap(root, dataset_id, references, *, split_id=None):
    base, sha, _, rows = load_snapshot(root, dataset_id)
    partitions = load_verified_split(root,dataset_id,split_id)[-1] if split_id else None
    ids = {r['record_id'] for r in rows}
    prompts = {r['prompt_id'] for r in rows}
    result = []
    for ref in references:
        with open_source(ref) as raw:
            ref_ids, ref_prompts = set(), set()
            for _, p in raw_files(raw):
                for _, row, _ in read_rows(p):
                    require(isinstance(row.get('record_id'),str) and isinstance(row.get('prompt_id'),str), 'Reference lacks record_id or prompt_id')
                    ref_ids.add(row['record_id']); ref_prompts.add(row['prompt_id'])
            entry = {'reference':str(ref), 'reference_unique_record_ids':len(ref_ids),
                     'shared_record_ids':len(ids & ref_ids),'shared_prompt_ids':sorted(prompts & ref_prompts)}
            if partitions is not None:
                entry['by_partition'] = {name:{'shared_record_ids':len({r['record_id'] for r in members} & ref_ids),
                    'shared_prompt_ids':sorted({r['prompt_id'] for r in members} & ref_prompts)} for name,members in partitions.items()}
            result.append(entry)
    return {'dataset_id':dataset_id,'dataset_manifest_sha256':sha,'references':result,
            'split_id':split_id,'independent_holdout_certified':False}


def assignment(rows, seed, weights, aliases):
    require(len(weights)==4 and all(type(w) is int and w>0 for w in weights) and sum(weights)==100, 'Four positive integer weights must sum to 100')
    require(type(seed) is int, 'Seed must be integer')
    require(isinstance(aliases,dict) and all(isinstance(k,str) and k.strip() and isinstance(v,str) and v.strip() for k,v in aliases.items()), 'Aliases must map prompt IDs to nonempty group IDs')
    eligible = [r for r in rows if not r['exclusion']]
    prompt_ids = {r['prompt_id'] for r in rows}
    require(set(aliases) <= prompt_ids, 'Alias mapping contains unknown prompt IDs')
    # An alias names a group, not another prompt. Namespace it to avoid collisions.
    groups = defaultdict(list)
    for r in eligible:
        pid = r['prompt_id']
        key = ('alias', aliases[pid]) if pid in aliases else ('prompt', pid)
        groups[key].append(r)
    require(len(groups)>=4, 'At least four eligible prompt groups required')
    strata = defaultdict(list)
    for group, members in groups.items():
        strata[tuple(sorted({r['prompt_set_version'] for r in members}))].append(group)
    # Search deterministic candidate allocations using only group/label coverage,
    # never classifier predictions. Keep the same per-stratum group quotas.
    group_models={key:{r['model_id'] for r in members} for key,members in groups.items()}
    all_models={r['model_id'] for r in eligible}
    best_score=float('inf')
    best_choices=None
    for attempt in range(COVERAGE_ATTEMPTS):
        choices={}
        covered={name:set() for name in PARTITIONS}
        for stratum, keys in sorted(strata.items()):
            ordered=sorted(keys,key=lambda k:(hashlib.sha256(json_text([seed,attempt,k]).encode()).hexdigest(),k))
            targets=[len(keys)*w for w in weights]
            counts=[n//100 for n in targets]
            for idx in sorted(range(4),key=lambda i:(-(targets[i]%100),i))[:len(keys)-sum(counts)]:
                counts[idx]+=1
            start=0
            for name,count in zip(PARTITIONS,counts):
                for key in ordered[start:start+count]:
                    choices[key]=name
                    covered[name].update(group_models[key])
                start+=count
        score=sum(len(all_models-covered[name]) for name in PARTITIONS)
        if score<best_score:
            best_score=score
            best_choices=choices
        if score==0:
            break
    choices=best_choices
    output = {p:[] for p in (*PARTITIONS,'excluded')}
    for r in rows:
        pid=r['prompt_id']; group=('alias',aliases[pid]) if pid in aliases else ('prompt',pid)
        name='excluded' if r['exclusion'] else choices[group]
        output[name].append({**r,'group_key':list(group)})
    return output


def panel_assignment(base, rows, prompt_set, probe_ids, persona_partitions):
    """Fixed query panel: partition entire personas, never individual samples.

    Exclude non-panel rows without changing raw data. Every model/persona/sample
    group must have exactly one eligible response per candidate probe. No
    synthetic imputation or selection of the easiest complete sessions.
    """
    require(component(prompt_set), 'Invalid prompt set version')
    require(isinstance(probe_ids,list) and 1 <= len(probe_ids) <= 30 and
            all(component(p) for p in probe_ids) and len(set(probe_ids))==len(probe_ids), 'Invalid probe pool')
    require(isinstance(persona_partitions,dict) and set(persona_partitions)==set(PARTITIONS), 'Supply all four persona partitions')
    require(all(isinstance(v,list) and v and all(component(p) for p in v) for v in persona_partitions.values()), 'Each partition needs persona IDs')
    personas=[p for v in persona_partitions.values() for p in v]
    require(len(set(personas))==len(personas),'Persona crosses partitions')
    partition_by_persona={p:name for name,ps in persona_partitions.items() for p in ps}
    raw_meta={}
    for _,path in raw_files(base/'raw'):
        for _,r,_ in read_rows(path):
            if r['prompt_set_version']==prompt_set and r['prompt_id'] in probe_ids:
                raw_meta[r['record_id']]=(r['persona_id'],r.get('sample_index'),r.get('run_type'),r.get('deployment_id'),r.get('temperature'),r.get('max_tokens'))
    out={p:[] for p in (*PARTITIONS,'excluded')}; groups=defaultdict(set); coverage=defaultdict(set)
    target_models={r['model_id'] for r in rows}; failed=[]
    for r in rows:
        record={**r}; rid=r['record_id']
        if rid not in raw_meta:
            record['exclusion']=r['exclusion'] or 'outside_fixed_probe_panel'; name='excluded'; key=['outside_panel',r['prompt_id']]
        else:
            persona,sample,run_type,deployment,temp,max_tokens=raw_meta[rid]
            require(persona in partition_by_persona, 'Panel contains persona absent from partition map')
            require(type(sample) is int and sample>=0, 'Panel requires nonnegative integer sample_index')
            # This protocol is for stateless library collection, not arbitrary deployment sessions.
            require(run_type=='library' and deployment is None, 'Panel requires library records, not deployment traces')
            key=['persona',persona]; name=partition_by_persona[persona]
            group=(r['model_id'],persona,sample,temp,max_tokens)
            if r['exclusion']:
                name='excluded'; failed.append((group,r['prompt_id']))
            else:
                require(r['prompt_id'] not in groups[group], 'Duplicate probe within panel sample group')
                groups[group].add(r['prompt_id']); coverage[(r['model_id'],persona)].add((sample,temp,max_tokens))
        out[name].append({**record,'group_key':key})
    require(all(pid in groups.get(group,set()) for group,pid in failed),'Failed panel probe has no successful retry')
    require(groups and all(v==set(probe_ids) for v in groups.values()), 'Incomplete probe panels; recollect missing/error probes')
    require(set(coverage)=={(m,p) for m in target_models for p in personas},'Missing model/persona panel coverage')
    # Same sample/configuration coverage everywhere prevents missingness leaking class labels.
    require(all(len({i[0] for i in v})==len(v) for v in coverage.values()),'Ambiguous multiple settings per sample')
    require(len({frozenset(i[0] for i in v) for v in coverage.values()})==1,'Unequal model/persona sample coverage')
    return out


def split_fixed_panel(root,dataset_id,split_id,*,prompt_set,probe_ids,persona_partitions):
    base,sha,report,rows=load_snapshot(root,dataset_id,eligibility_policy=CURRENT_ELIGIBILITY)
    output=panel_assignment(base,rows,prompt_set,probe_ids,persona_partitions)
    destination=split_dir(base,split_id); partitions={}; models={r['model_id'] for r in rows}
    with publish_new(destination) as stage:
        for name,members in output.items():
            path=stage/(name+'.jsonl')
            with path.open('x',encoding='utf-8',newline='\n') as f:
                for r in members: f.write(json.dumps(r,sort_keys=True,ensure_ascii=True)+'\n')
            counts=Counter(r['model_id'] for r in members)
            partitions[name]={'records':len(members),'groups':len({tuple(r['group_key']) for r in members}),
                'sha256':digest(path),'by_model':dict(counts),'missing_models':sorted(models-set(counts)),
                'by_prompt_set':dict(Counter(r['prompt_set_version'] for r in members))}
        manifest={'schema_version':'1.0','status':'candidate_split_not_certified_holdout','dataset_id':dataset_id,
            'dataset_manifest_sha256':sha,'catalog_sha256':report['catalog_sha256'],'split_id':split_id,
            'algorithm':PANEL_ALGORITHM,'eligibility_policy':CURRENT_ELIGIBILITY,'prompt_set_version':prompt_set,
            'probe_pool':probe_ids,'persona_partitions':persona_partitions,'partitions':partitions,
            'warnings':['Fixed probes intentionally repeat across partitions; personas do not.',
                        'Trace groups are reconstructed from model/persona/sample/config metadata, not recorded session IDs.',
                        'No independent holdout or unknown-family certification; check historical overlaps.']}
        write_new(stage/'split_manifest.json',json_text(manifest))
    return manifest


def split_dir(base, split_id):
    require(component(split_id), 'Invalid split ID')
    path=base/'splits'/split_id
    require(not (base/'splits').is_symlink() and not path.is_symlink(), 'Symlinked split path')
    return path


def split(root, dataset_id, split_id, *, seed=42, weights=DEFAULT_WEIGHTS, aliases=None, eligibility_policy=CURRENT_ELIGIBILITY):
    base, sha, report, rows = load_snapshot(root, dataset_id, eligibility_policy=eligibility_policy)
    aliases = {} if aliases is None else aliases
    output = assignment(rows,seed,weights,aliases)
    destination=split_dir(base,split_id)
    models=sorted({r['model_id'] for r in rows})
    partitions={}
    with publish_new(destination) as stage:
        for name, members in output.items():
            path=stage/(name+'.jsonl')
            with path.open('x',encoding='utf-8',newline='\n') as f:
                for r in members: f.write(json.dumps(r,sort_keys=True,ensure_ascii=True)+'\n')
            counts=Counter(r['model_id'] for r in members)
            partitions[name]={'records':len(members),'groups':len({tuple(r['group_key']) for r in members}),
                              'sha256':digest(path),'by_model':dict(counts),'missing_models':sorted(set(models)-set(counts)),
                              'by_prompt_set':dict(Counter(r['prompt_set_version'] for r in members))}
        manifest={'schema_version':'1.0','status':'candidate_split_not_certified_holdout','dataset_id':dataset_id,
                  'dataset_manifest_sha256':sha,'catalog_sha256':report['catalog_sha256'],'split_id':split_id,
                  'algorithm':ALGORITHM,'eligibility_policy':eligibility_policy,'seed':seed,'coverage_search_attempt_limit':COVERAGE_ATTEMPTS,
                  'weights_percent':dict(zip(PARTITIONS,weights)),'prompt_aliases':aliases,'partitions':partitions,
                  'warnings':['Blank responses without errors are eligible under v2, not proof of intentional refusal; inspect provider metadata.',
                              'Raw prompt text is absent; different prompt IDs can still represent identical/related prompts.',
                              'Review overlaps with previous training/reference/evaluation data and prompt definitions.',
                              'Weights apply to eligible prompt groups, not individual records. Coverage search minimizes missing model/partition pairs but cannot guarantee coverage.',
                              'This does not create complete multi-probe sessions or certify unknown-family evaluation.']}
        write_new(stage/'split_manifest.json',json_text(manifest))
    return manifest


def verified_split(base,dataset_id,sha,rows,split_id):
    directory=split_dir(base,split_id)
    mp=directory/'split_manifest.json'
    require(mp.is_file() and not mp.is_symlink(),'Missing or symlinked split manifest')
    manifest=read_json(mp)
    require(manifest.get('dataset_id')==dataset_id and manifest.get('split_id')==split_id and manifest.get('dataset_manifest_sha256')==sha,'Split manifest mismatch')
    if manifest.get('algorithm')==PANEL_ALGORITHM:
        require(manifest.get('eligibility_policy')==CURRENT_ELIGIBILITY,'Fixed panel eligibility policy mismatch')
        generated=panel_assignment(base,rows,manifest['prompt_set_version'],manifest['probe_pool'],manifest['persona_partitions'])
    else:
        require(manifest.get('algorithm')==ALGORITHM and manifest.get('coverage_search_attempt_limit')==COVERAGE_ATTEMPTS,'Split algorithm mismatch')
        generated=assignment(rows,manifest['seed'],tuple(manifest['weights_percent'][p] for p in PARTITIONS),manifest['prompt_aliases'])
    for name,members in generated.items():
        path=directory/(name+'.jsonl')
        require(path.is_file() and not path.is_symlink(),'Missing or symlinked split assignment')
        actual=[r for _,r,_ in read_rows(path)]
        require(actual==members and digest(path)==manifest['partitions'][name]['sha256'],'Split assignment changed')
    return directory,generated


def load_verified_split(root,dataset_id,split_id):
    """Respect historical split policy; never reinterpret an existing assignment."""
    base=dataset_dir(root,dataset_id)
    mp=split_dir(base,split_id)/'split_manifest.json'
    require(mp.is_file() and not mp.is_symlink(),'Missing or symlinked split manifest')
    manifest=read_json(mp)
    policy=manifest.get('eligibility_policy',LEGACY_ELIGIBILITY)
    base,sha,report,rows=load_snapshot(root,dataset_id,eligibility_policy=policy)
    directory,generated=verified_split(base,dataset_id,sha,rows,split_id)
    return base,sha,report,directory,generated


def inspect_snapshot(root,dataset_id,split_id=None):
    if split_id is None:
        base,sha,report,_=load_snapshot(root,dataset_id)
        return {**report,'dataset_id':dataset_id,'dataset_manifest_sha256':sha}
    base,sha,report,directory,generated=load_verified_split(root,dataset_id,split_id)
    split_meta=read_json(directory/'split_manifest.json')
    return {'dataset_id':dataset_id,'dataset_manifest_sha256':sha,'split_id':split_id,
            'split_algorithm':split_meta['algorithm'],
            'probe_pool':split_meta.get('probe_pool'), 'prompt_set_version':split_meta.get('prompt_set_version'),
            'persona_partitions':split_meta.get('persona_partitions'),
            'split_manifest_sha256':digest(directory/'split_manifest.json'),
            'eligibility_policy':report['eligibility_policy'],'summary':report['summary'],
            'partitions':{k:{'records':len(v),'models':sorted({r['model_id'] for r in v})} for k,v in generated.items()},
            'independent_holdout_certified':False}


def export(root,dataset_id,split_id,partition,output):
    require(partition in PARTITIONS,'Only eligible partitions can be exported')
    base,sha,_,directory,generated=load_verified_split(root,dataset_id,split_id)
    selected={r['record_id'] for r in generated[partition]}
    output=Path(output)
    require(not output.resolve().is_relative_to(base.resolve()), 'Export outside immutable dataset snapshot')
    output.parent.mkdir(parents=True,exist_ok=True)
    require(not output.exists() and not output.is_symlink(),'Export destination already exists')
    # Stage before publication; exclusive destination creation prevents overwrites.
    with tempfile.TemporaryFile() as tmp:
        count=0
        for _,path in raw_files(base/'raw'):
            for _,row,line in read_rows(path):
                if row['record_id'] in selected:
                    tmp.write(line if line.endswith(b'\n') else line+b'\n');count+=1
        require(count==len(selected),'Export membership mismatch')
        tmp.seek(0)
        with output.open('xb') as dest: shutil.copyfileobj(tmp,dest)
    return {'partition':partition,'records':count,'sha256':digest(output),'split_manifest_sha256':digest(directory/'split_manifest.json')}
