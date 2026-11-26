"""Exercise lifecycle with a non-executable synthetic bundle, never claim training."""
from __future__ import annotations
import json,shutil,tempfile,unittest
from pathlib import Path
from fingerprinting.training import orchestrator as o
from fingerprinting.onboarding import datasets as d,artifacts as a
ROOT=(Path(__file__).resolve().parents[2] / 'system')

class FakeTrainer:
    def __init__(self,source,behavior='success'):self.source=source;self.behavior=behavior;self.context=None
    def run(self,ctx):
        self.context=ctx
        assert not (ctx.train_jsonl.parent/'test.jsonl').exists()
        assert not (ctx.train_jsonl.parent/'calibration.jsonl').exists()
        train=[json.loads(line) for line in ctx.train_jsonl.read_text().splitlines()]
        val=[json.loads(line) for line in ctx.validation_jsonl.read_text().splitlines()]
        assert not ({r['prompt_id'] for r in train}&{r['prompt_id'] for r in val})
        if self.behavior=='fail':raise RuntimeError('synthetic training failure')
        if self.behavior=='mutate':ctx.train_jsonl.write_text('changed')
        for name in ('feature_extractor.py','feature_manifest.json'):
            shutil.copyfile(self.source/name,ctx.output_dir/name)
        (ctx.output_dir/'classifier.joblib').write_bytes(b'NON-EXECUTABLE TEST FIXTURE')
        m=a.read_json(self.source/'manifest.json');m['artifact_id']=ctx.artifact_id if self.behavior!='wrong' else 'random_forest/v99'
        m['supported_models']=sorted({r['model_key'] for r in train});m['options']['label_order']=m['supported_models']
        for item in m['required_files']:item['sha256']=None
        m['provenance']={'source':'synthetic fixture only','training_code_revision':'test','runtime_dependencies':{'python':'test'}}
        if self.behavior=='provenance':m['provenance']['split_manifest_sha256']='0'*64
        (ctx.output_dir/'manifest.json').write_text(json.dumps(m))

class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);home=Path(self.tmp.name);self.root=home/'system';self.root.mkdir()
        for name in ('catalog','config'):shutil.copytree(ROOT/name,self.root/name)
        (self.root/'models').mkdir();shutil.copyfile(ROOT/'models/registry.json',self.root/'models/registry.json')
        for rel in a.read_json(ROOT/'models/registry.json')['artifacts'].values():
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,p)
        self.source=ROOT/'models/random_forest/v1';self.dataset='collector_raw/test';self.split='s1'
        for model in ('llama3.1-8b','gemma3-4b'):
            path=home/'raw'/model/'fingerprint_v0.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
            rows=[dict(record_id=f'{model}-{i}',model_key=model,prompt_id=f'p{i}',prompt_set_version='fingerprint_v0',prompt_group='x',persona_id='none',response_text='' if i==0 else 'ok',error=None) for i in range(20)]
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        d.register(self.root,home/'raw','test',source_note='synthetic');d.split(self.root,self.dataset,self.split)
        self.config={'dataset_id':self.dataset,'split_id':self.split,'methods':{'random_forest':{'artifact_id':'random_forest/test-candidate','parameters':{'seed':42}}}}
        self.prod=(self.root/'config/production.yaml').read_bytes();self.reg=(self.root/'models/registry.json').read_bytes()
    def test_plan_blocked_no_side_effect(self):
        p=o.plan(self.root,self.config,{})
        self.assertEqual(p['methods']['random_forest']['status'],'blocked_trainer_not_integrated');self.assertFalse((self.root/'.local').exists());self.assertFalse(p['independent_holdout_certified'])
    def test_no_approval(self):
        with self.assertRaisesRegex(o.TrainingError,'approve-dataset'):o.run(self.root,self.config,{})
        self.assertFalse((self.root/'.local').exists())
    def test_no_trainers_records_blocked(self):
        r=o.run(self.root,self.config,{},approve_dataset=True)
        self.assertEqual(r['status'],'blocked');self.assertEqual(o.history(self.root)[0]['status'],'blocked');self.assertNotIn('exports',r)
    def test_candidate_and_provenance(self):
        trainer=FakeTrainer(self.source);r=o.run(self.root,self.config,{'random_forest':trainer},approve_dataset=True)
        self.assertEqual(r['status'],'completed',r);self.assertEqual(r['methods']['random_forest']['status'],'candidate_validated')
        self.assertFalse(trainer.context.train_jsonl.exists());self.assertFalse(trainer.context.validation_jsonl.exists())
        p=a.read_json(trainer.context.output_dir/'manifest.json')['provenance'];self.assertEqual(p['split_manifest_sha256'],r['split_manifest_sha256']);self.assertEqual(p['training_run_id'],r['run_id']);self.assertEqual(p['eligibility_policy'],d.CURRENT_ELIGIBILITY)
        self.assertEqual((self.root/'models/registry.json').read_bytes(),self.reg);self.assertEqual((self.root/'config/production.yaml').read_bytes(),self.prod)
    def test_register_candidate_not_activate(self):
        r=o.run(self.root,self.config,{'random_forest':FakeTrainer(self.source)},approve_dataset=True,register_candidates=True)
        self.assertEqual(r['status'],'completed',r);self.assertEqual(r['methods']['random_forest']['status'],'registered_candidate');self.assertTrue((self.root/'models/random_forest/test-candidate/manifest.json').exists());self.assertEqual((self.root/'config/production.yaml').read_bytes(),self.prod)
        self.assertEqual(o.plan(self.root,self.config,{'random_forest':FakeTrainer(self.source)})['methods']['random_forest']['status'],'blocked_existing_version')
    def test_failure_does_not_register(self):
        for behavior in ('fail','mutate','wrong','provenance'):
            with self.subTest(behavior=behavior):
                r=o.run(self.root,self.config,{'random_forest':FakeTrainer(self.source,behavior)},approve_dataset=True,register_candidates=True)
                self.assertEqual(r['status'],'failed',r);self.assertEqual((self.root/'models/registry.json').read_bytes(),self.reg);self.assertFalse((self.root/'models/random_forest/test-candidate').exists())
    def test_batch_partial_and_manual(self):
        self.config['methods']['lora']={'artifact_id':'lora/v3','parameters':{}}
        t={'random_forest':FakeTrainer(self.source)}
        r=o.run(self.root,self.config,t,approve_dataset=True);self.assertEqual(r['status'],'partial',r)
        self.assertEqual(o.run(self.root,self.config,t,method='random_forest',approve_dataset=True)['status'],'completed')
    def test_config_validation(self):
        for bad in ('../../escape','lora/v3','random_forest/../evil'):
            self.config['methods']['random_forest']['artifact_id']=bad
            with self.assertRaises(o.TrainingError):o.plan(self.root,self.config,{})
    def test_tampered_split_refused(self):
        path=self.root/'datasets'/self.dataset/'splits'/self.split/'train.jsonl';path.write_text('')
        with self.assertRaises(d.DatasetError):o.plan(self.root,self.config,{})
    def test_template_pins_verified_split(self):
        path=Path(self.tmp.name)/'template.json';a.template(self.root,'random_forest/v1','random_forest/test-candidate',path,dataset_id=self.dataset,split_id=self.split)
        p=a.read_json(path)['provenance'];self.assertEqual(p['split_manifest_sha256'],d.inspect_snapshot(self.root,self.dataset,self.split)['split_manifest_sha256']);self.assertEqual(p['source'],'TODO')
    def test_split_provenance_hash_checked(self):
        trainer=FakeTrainer(self.source);r=o.run(self.root,self.config,{'random_forest':trainer},approve_dataset=True)
        p=trainer.context.output_dir/'manifest.json';raw=a.read_json(p);raw['provenance']['split_manifest_sha256']='0'*64;p.write_text(json.dumps(raw))
        with self.assertRaisesRegex(a.OnboardingError,'split manifest hash'):a.validate(self.root,trainer.context.output_dir)
    def test_interrupted_history(self):
        folder=self.root/'.local/training_runs/interrupted';folder.mkdir(parents=True);(folder/'plan.json').write_text('{"run_id":"interrupted","status":"running"}')
        self.assertEqual(o.history(self.root)[0]['status'],'incomplete_or_interrupted')

if __name__=='__main__':unittest.main()
