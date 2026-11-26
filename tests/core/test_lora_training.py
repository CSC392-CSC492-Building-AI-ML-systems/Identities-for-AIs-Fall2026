"""Offline trainer/data/export tests. Synthetic fit is not real PEFT training."""
import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from fingerprinting.training import lora as l,orchestrator as o
from fingerprinting.onboarding import datasets as d,artifacts as a
from fingerprinting.adapters.lora_preprocessing import BLANK_POLICY,LEGACY_POLICY,EMPTY_MARKER,prepare_response
from fingerprinting.adapters.lora import LoRAIdentifier,LoRAConfigurationError

ROOT=(Path(__file__).resolve().parents[2] / 'system')
LABELS=['gemma3-4b','llama3.1-8b']

class LoRATrainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name)
        self.train=self.home/'train.jsonl';self.val=self.home/'validation.jsonl'
        self.params=l.parameters({'base_model_revision':'a'*40})
        self.rows(self.train,'train','p1');self.rows(self.val,'val','p2')
    def rows(self,path,tag,prompt,extra=False):
        rows=[dict(record_id=f'{tag}-{m}-{i}',model_key=m,prompt_id=prompt,prompt_set_version='fingerprint_v0',persona_id=tag,response_text=None if i==0 else ' response ',error=None) for m in LABELS for i in range(2)]
        if extra:rows+=[dict(rows[0],record_id=tag+'extra',prompt_id='exclusive')]
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows));return rows
    def test_legacy_and_blank_marker(self):
        self.assertEqual(prepare_response('  ',LEGACY_POLICY),'');self.assertEqual(prepare_response(None,BLANK_POLICY),EMPTY_MARKER)
        self.assertNotEqual(prepare_response(EMPTY_MARKER,BLANK_POLICY),EMPTY_MARKER);self.assertEqual(prepare_response('  hello ',BLANK_POLICY),'hello')
        self.assertNotEqual(prepare_response('\\'+EMPTY_MARKER,BLANK_POLICY),prepare_response(EMPTY_MARKER,BLANK_POLICY))
    def test_pinned_revision_required(self):
        for revision in (None,'main','not-a-commit'):
            with self.assertRaisesRegex(ValueError,'40-character'):l.parameters({'base_model_revision':revision})
    def test_bad_parameters(self):
        for params in ({'epochs':True},{'device':'cpu','precision':'fp16'},{'max_tokens':0},{'lora_rank':0},{'base_model':'random'},{'learning_rate':float('nan')},{'unknown':1},{'model_ids':['x','x']}):
            with self.subTest(params=params),self.assertRaises(ValueError):l.parameters({'base_model_revision':'a'*40,**params})
    def test_balanced_and_blank(self):
        self.rows(self.train,'train','p1',True)
        train,val,labels,r=l.prepare_data(self.train,self.val,self.params,d.ALGORITHM)
        self.assertEqual(labels,LABELS);self.assertEqual(r['train']['retained_rows'],4);self.assertEqual(r['train']['dropped_rows'],1);self.assertEqual(r['train']['blank_rows'],2)
        self.assertEqual([x['id'] for x in train],[x['id'] for x in l.prepare_data(self.train,self.val,self.params,d.ALGORITHM)[0]])
        self.assertTrue(all(x['text'] for x in train));self.assertFalse(r['test_used'])
    def test_cap_balanced(self):
        p={**self.params,'max_train_per_class':1};train,_,_,r=l.prepare_data(self.train,self.val,p,d.ALGORITHM);self.assertEqual(len(train),2);self.assertEqual(r['train']['class_counts'],dict.fromkeys(LABELS,1))
    def test_prompt_and_persona_leakage(self):
        self.rows(self.val,'val','p1')
        with self.assertRaisesRegex(ValueError,'Prompt leakage'):l.prepare_data(self.train,self.val,self.params,d.ALGORITHM)
        self.assertEqual(len(l.prepare_data(self.train,self.val,self.params,d.PANEL_ALGORITHM)[0]),4)
        rows=self.rows(self.val,'val','p1');self.val.write_text(''.join(json.dumps(dict(r,persona_id='train'))+'\n' for r in rows))
        with self.assertRaisesRegex(ValueError,'Persona leakage'):l.prepare_data(self.train,self.val,self.params,d.PANEL_ALGORITHM)
    def test_record_leakage(self):
        self.val.write_bytes(self.train.read_bytes())
        with self.assertRaisesRegex(ValueError,'Record leakage'):l.prepare_data(self.train,self.val,self.params,d.ALGORITHM)
    def test_no_shared_prompts_refused(self):
        rows=self.rows(self.train,'train','p1');self.train.write_text(''.join(json.dumps(dict(r,prompt_id=r['model_key']))+'\n' for r in rows))
        with self.assertRaisesRegex(ValueError,'No shared prompt'):l.prepare_data(self.train,self.val,self.params,d.ALGORITHM)
    def test_error_excluded_by_export_contract(self):
        rows=self.rows(self.train,'train','p1');rows[0]['error']='failure';self.train.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        with self.assertRaisesRegex(ValueError,'collection error'):l.load_rows(self.train)
    def test_new_input_policy_and_legacy(self):
        m=a.existing(ROOT).get('lora/v2');self.assertEqual(LoRAIdentifier(m,predictor=lambda _:[]).input_policy,LEGACY_POLICY)
        m=replace(m,options={**m.options,'input_policy':BLANK_POLICY});self.assertEqual(LoRAIdentifier(m,predictor=lambda _:[]).input_policy,BLANK_POLICY)
        with self.assertRaises(LoRAConfigurationError):LoRAIdentifier(replace(m,options={**m.options,'input_policy':'invalid'}))
    def test_available_and_protocols(self):
        t=o.available_trainers()['lora'];self.assertTrue(t.supports({'split_algorithm':d.PANEL_ALGORITHM}));self.assertFalse(t.supports({'split_algorithm':'wrong'}))
        with self.assertRaises(ValueError):t.check_parameters({})
    def test_synthetic_orchestration_register(self):
        # Build a temporary actual dataset/registry, then use synthetic tensors
        # to test file contract and registration; never claim trained weights.
        import numpy as np
        from safetensors.numpy import save_file
        root=self.home/'system';root.mkdir()
        for name in ('catalog','config'):shutil.copytree(ROOT/name,root/name)
        index=a.read_json(ROOT/'models/registry.json');(root/'models').mkdir();shutil.copyfile(ROOT/'models/registry.json',root/'models/registry.json')
        for rel in index['artifacts'].values():
            path=root/rel;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,path)
        for m in LABELS:
            path=self.home/'raw'/m/'fingerprint_v0.jsonl';path.parent.mkdir(parents=True)
            path.write_text(''.join(json.dumps(dict(record_id=f'{m}-{i}',model_key=m,prompt_id=f'p{i}',prompt_set_version='fingerprint_v0',prompt_group='x',persona_id='none',response_text='' if m==LABELS[0] else 'ok',error=None))+'\n' for i in range(20)))
        d.register(root,self.home/'raw','fixture',source_note='synthetic');d.split(root,'collector_raw/fixture','s1')
        cfg={'dataset_id':'collector_raw/fixture','split_id':'s1','methods':{'lora':{'artifact_id':'lora/test-training','parameters':{'base_model_revision':'a'*40}}}}
        prod=(root/'config/production.yaml').read_bytes()
        def fake(ctx,p,train,val,labels):
            self.assertEqual(labels,LABELS);self.assertFalse((ctx.train_jsonl.parent/'test.jsonl').exists());self.assertTrue(all(x['text'] for x in train))
            (ctx.output_dir/'adapter_config.json').write_text(json.dumps({'task_type':'SEQ_CLS','peft_type':'LORA','base_model_name_or_path':p['base_model'],'r':p['lora_rank'],'lora_alpha':p['lora_alpha']}))
            save_file({'base.score.weight':np.zeros((2,4),dtype=np.float32),'base.lora_A.weight':np.zeros((1,4),dtype=np.float32),'base.lora_B.weight':np.zeros((4,1),dtype=np.float32)},str(ctx.output_dir/'adapter_model.safetensors'))
            return [2,4],{'synthetic':True},{'python':'fixture'}
        with patch.object(l,'fit_export',side_effect=fake):r=o.run(root,cfg,o.available_trainers(),approve_dataset=True,register_candidates=True)
        self.assertEqual(r['status'],'completed',r);m=a.existing(root).get('lora/test-training');self.assertEqual(m.options['label_order'],LABELS);self.assertEqual(m.options['input_policy'],BLANK_POLICY);self.assertEqual(m.options['acceptance_policy'],{'mode':'review_only'});self.assertFalse(m.provenance['runtime_reload_validated']);self.assertEqual((root/'config/production.yaml').read_bytes(),prod)
        # Exercise the held-out evaluator with a synthetic predictor, not real HF weights.
        from tools import evaluate_lora_split as ev
        from fingerprinting.factory import AdapterConstructors
        yaml=root/'config/experiments/lora-test.yaml';a.candidate_config(root,'lora/test-training',yaml,single=True)
        constructors=AdapterConstructors();seen=[]
        def predict(text):
            seen.append(text);return [.8,.2]
        constructors.register_stage2('lora',lambda manifest,choice:LoRAIdentifier(manifest,predictor=predict))
        with patch.object(ev,'real_adapter_constructors',return_value=constructors):
            evaluation=ev.evaluate(root,yaml,self.home/'test-result.json')
        self.assertEqual(evaluation['pipeline_metrics']['accepted'],0);self.assertEqual(evaluation['test_data']['retained_rows'],len(seen));self.assertIn('',seen)
        self.assertFalse(evaluation['independent_holdout_certified'])
        cfg['methods']['lora']['artifact_id']='lora/test-blocked';cfg['methods']['lora']['parameters']={}
        self.assertEqual(o.plan(root,cfg,o.available_trainers())['methods']['lora']['status'],'blocked_invalid_parameters')

if __name__=='__main__':unittest.main()
