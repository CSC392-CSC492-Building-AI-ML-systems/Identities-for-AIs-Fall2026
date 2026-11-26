"""Offline tests for versioned collector snapshots and deterministic split membership."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from collections import Counter

from fingerprinting.onboarding import datasets as d
from fingerprinting.onboarding.artifacts import digest

ROOT=(Path(__file__).resolve().parents[2] / 'system')


class DatasetOnboardingTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.home=Path(tmp.name);self.root=self.home/'system';self.root.mkdir()
        shutil.copytree(ROOT/'catalog',self.root/'catalog')
        self.source=self.home/'source';self.raw=self.source/'raw'
        self.model='llama3.1-8b';self.model2='gemini-3.1-pro';self.version='training_v1'
        self.dataset='collector_raw/test-v1'
        self.records={}
        for model in (self.model,self.model2):
            rows=[self.row(model,f'p{i}',j) for i in range(20) for j in range(2)]
            rows.append(self.row(model,'p0',2,error='timeout',response_text=None))
            rows.append(self.row(model,'p1',2,response_text=' ',reasoning_text='separate'))
            self.records[model]=rows
            self.save(model)
    def row(self,model,prompt,n,**extra):
        return dict(record_id=f'{model}-{prompt}-{n}',model_key=model,prompt_set_version=self.version,
                    prompt_id=prompt,prompt_group='source_category',persona_id=f'P{n}',response_text='hello',error=None,**{}) | extra
    def path(self,model):return self.raw/model/(self.version+'.jsonl')
    def save(self,model):
        p=self.path(model);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(''.join(json.dumps(x)+'\n' for x in self.records[model]),encoding='utf-8')
    def register(self):return d.register(self.root,self.source,'test-v1',source_note='fixture')
    def snapshot(self):return self.root/'datasets'/self.dataset
    def splits(self,name='test-split',**kwargs):
        return d.split(self.root,self.dataset,name,**kwargs)
    def members(self,name,part):
        return [json.loads(x) for x in (self.snapshot()/'splits'/name/(part+'.jsonl')).read_text().splitlines()]
    def archive(self):
        path=self.home/'fixture.zip'
        with zipfile.ZipFile(path,'w') as z:
            for f in self.raw.rglob('*.jsonl'):z.write(f,f.relative_to(self.source).as_posix())
        return path
    def test_validate_counts_and_no_writes(self):
        s=d.validate(self.root,self.source)['summary']
        self.assertEqual((s['records'],s['eligible'],s['recorded_errors'],s['blank_without_error']),(84,82,2,2))
        self.assertEqual(s['blank_with_reasoning'],2);self.assertEqual(s['distinct_prompt_ids'],20)
        self.assertFalse((self.root/'datasets').exists())
    def test_blank_rows_eligible_and_historical_policy_reproducible(self):
        self.register();self.splits('new');self.splits('old',eligibility_policy=d.LEGACY_ELIGIBILITY)
        self.assertEqual(len(self.members('new','excluded')),2)
        self.assertEqual(len(self.members('old','excluded')),4)
        # Previous manifests had no explicit policy field.
        mp=self.snapshot()/'splits/old/split_manifest.json'
        m=json.loads(mp.read_text());del m['eligibility_policy'];mp.write_text(json.dumps(m))
        self.assertEqual(d.inspect_snapshot(self.root,self.dataset,'old')['eligibility_policy'],d.LEGACY_ELIGIBILITY)
        self.assertEqual(d.inspect_snapshot(self.root,self.dataset,'new')['eligibility_policy'],d.CURRENT_ELIGIBILITY)
    def test_raw_directory_and_zip_equivalent(self):
        self.assertEqual(d.validate(self.root,self.raw),d.validate(self.root,self.archive()))
    def test_register_preserves_original_bytes_and_manifest(self):
        result=self.register();dest=self.snapshot();manifest=json.loads((dest/'manifest.json').read_text())
        self.assertEqual(result['manifest_sha256'],digest(dest/'manifest.json'))
        self.assertEqual(manifest['dataset_id'],self.dataset);self.assertEqual(manifest['license_review'],'pending')
        for f in self.raw.rglob('*.jsonl'):self.assertEqual(f.read_bytes(),(dest/'raw'/f.relative_to(self.raw)).read_bytes())
    def test_register_zip_records_archive_digest(self):
        z=self.archive();d.register(self.root,z,'test-v1',source_note='fixture')
        self.assertEqual(json.loads((self.snapshot()/'manifest.json').read_text())['source_archive_sha256'],digest(z))
    def test_duplicate_registration_refused(self):
        self.register();before=digest(self.snapshot()/'manifest.json')
        with self.assertRaises(d.DatasetError):self.register()
        self.assertEqual(before,digest(self.snapshot()/'manifest.json'))
    def test_duplicate_id_refused_and_no_partial_snapshot(self):
        self.records[self.model].append(self.records[self.model][0]);self.save(self.model)
        with self.assertRaisesRegex(d.DatasetError,'duplicate record_id'):self.register()
        self.assertFalse(self.snapshot().exists())
    def test_mismatched_model_and_prompt_set(self):
        for field,value in [('model_key',self.model2),('prompt_set_version','wrong')]:
            with self.subTest(field=field):
                original=self.records[self.model][0][field];self.records[self.model][0][field]=value;self.save(self.model)
                with self.assertRaisesRegex(d.DatasetError,'mismatch'):d.validate(self.root,self.raw)
                self.records[self.model][0][field]=original;self.save(self.model)
    def test_unknown_model(self):
        self.path(self.model).rename(self.path(self.model).with_name('other.jsonl'))
        self.path(self.model).parent.rename(self.raw/'not-a-model')
        with self.assertRaisesRegex(d.DatasetError,'Unknown canonical'):d.validate(self.root,self.source)
    def test_malformed_json_and_invalid_types(self):
        for line in ['bad','{"x":1,"x":2}','{"x":NaN}','[]',' ',json.dumps(self.records[self.model][0]|{'response_text':123})]:
            with self.subTest(line=line[:20]):
                self.path(self.model).write_text(line+'\n')
                with self.assertRaises(d.DatasetError):d.validate(self.root,self.source)
    def test_repeated_exact_response_is_reported_not_removed(self):
        self.records[self.model].append(self.records[self.model][0]|{'record_id':'unique-repeat'});self.save(self.model)
        s=d.validate(self.root,self.source)['summary'];self.assertEqual(s['eligible'],83)
        self.assertEqual(s['repeated_exact_responses_same_model_prompt_persona'],1)
    def test_unsafe_zip_paths_refused(self):
        for name in ('../bad.jsonl','raw/../../bad.jsonl','raw/a/b/extra.jsonl','raw/a/CON.jsonl','raw/a\\b/c.jsonl','/raw/a/b.jsonl'):
            with self.subTest(name=name):
                z=self.home/'bad.zip'
                with zipfile.ZipFile(z,'w') as f:f.writestr(name,'{}')
                with self.assertRaises(d.DatasetError):d.validate(self.root,z)
    def test_zip_duplicate_member_refused(self):
        z=self.home/'bad.zip'
        with warnings.catch_warnings(),zipfile.ZipFile(z,'w') as f:
            warnings.simplefilter('ignore');f.writestr('raw/a/b.jsonl','{}');f.writestr('raw/a/b.jsonl','{}')
        with self.assertRaisesRegex(d.DatasetError,'Duplicate ZIP'):d.validate(self.root,z)
    def test_zip_symlink_refused(self):
        z=self.home/'bad.zip';info=zipfile.ZipInfo('raw/a/b.jsonl');info.create_system=3;info.external_attr=0o120777<<16
        with zipfile.ZipFile(z,'w') as f:f.writestr(info,'target')
        with self.assertRaisesRegex(d.DatasetError,'Unsupported ZIP'):d.validate(self.root,z)
    def test_split_reproducible_and_group_disjoint(self):
        self.register();a=self.splits('a',seed=11);b=self.splits('b',seed=11)
        self.assertEqual(a['partitions'],b['partitions']);self.assertEqual(a['status'],'candidate_split_not_certified_holdout')
        seen=set();all_ids=set()
        for part in d.PARTITIONS:
            members=self.members('a',part);ids={r['record_id'] for r in members};prompts={r['prompt_id'] for r in members}
            self.assertFalse(seen & prompts);seen.update(prompts);self.assertFalse(all_ids & ids);all_ids.update(ids)
            self.assertEqual({r['model_id'] for r in members},{self.model,self.model2})
        self.assertEqual(len(all_ids),82);self.assertEqual(len(self.members('a','excluded')),2)
        self.assertEqual(len(seen),20)
    def test_shared_prompt_ids_across_versions_and_aliases(self):
        # New set repeats p0 and includes differently named p1 alias. All mapped
        # IDs must be assigned together even across versions and models.
        rows=[self.row(self.model,'p0',10),self.row(self.model,'p-alias',10)]
        path=self.raw/self.model/'other.jsonl';path.write_text(''.join(json.dumps(r|{'prompt_set_version':'other'})+'\n' for r in rows))
        self.register();self.splits(aliases={'p0':'duplicate-text','p-alias':'duplicate-text'})
        locations={part for part in d.PARTITIONS if any(r['prompt_id'] in ('p0','p-alias') for r in self.members('test-split',part))}
        self.assertEqual(len(locations),1)
    def test_split_refuses_invalid_alias_weights_and_overwrite(self):
        self.register()
        for kwargs in ({'weights':(1,2,3,4)},{'aliases':{'not-known':'alias'}}):
            with self.assertRaises(d.DatasetError):self.splits(**kwargs)
        self.splits()
        with self.assertRaises(d.DatasetError):self.splits()
    def test_missing_model_coverage_reported(self):
        self.records[self.model2]=self.records[self.model2][:1];self.save(self.model2)
        self.register();s=self.splits()
        self.assertEqual(sum(self.model2 in s['partitions'][p]['missing_models'] for p in d.PARTITIONS),3)
    def test_tampered_snapshot_refused(self):
        self.register();p=self.snapshot()/'raw'/self.model/(self.version+'.jsonl')
        p.write_text(p.read_text().replace('hello','changed',1))
        with self.assertRaisesRegex(d.DatasetError,'differs'):self.splits()
    def test_export_only_selected_original_rows(self):
        self.register();self.splits();out=self.home/'train.jsonl';r=d.export(self.root,self.dataset,'test-split','train',out)
        original={x['record_id']:x for rows in self.records.values() for x in rows};exported=[json.loads(l) for l in out.read_text().splitlines()]
        self.assertEqual(r['records'],len(exported));self.assertEqual({x['record_id'] for x in exported},{x['record_id'] for x in self.members('test-split','train')})
        for row in exported:self.assertEqual(row,original[row['record_id']])
        with self.assertRaises(d.DatasetError):d.export(self.root,self.dataset,'test-split','train',out)
    def test_export_refuses_tampered_assignment(self):
        self.register();self.splits();path=self.snapshot()/'splits/test-split/train.jsonl';path.write_text('')
        with self.assertRaisesRegex(d.DatasetError,'assignment changed'):d.export(self.root,self.dataset,'test-split','train',self.home/'out.jsonl')
    def test_audit_overlap_by_partition(self):
        self.register();self.splits();audit=d.overlap(self.root,self.dataset,[self.source],split_id='test-split')
        ref=audit['references'][0];self.assertEqual(ref['shared_record_ids'],84)
        self.assertEqual(sum(v['shared_record_ids'] for v in ref['by_partition'].values()),84);self.assertFalse(audit['independent_holdout_certified'])
    def test_invalid_dataset_path_refused(self):
        with self.assertRaises(d.DatasetError):d.register(self.root,self.source,'../escape',source_note='fixture')
    def test_export_refuses_write_inside_snapshot(self):
        self.register();self.splits()
        with self.assertRaises(d.DatasetError):d.export(self.root,self.dataset,'test-split','train',self.snapshot()/'raw'/'new.jsonl')


if __name__=='__main__':unittest.main()
