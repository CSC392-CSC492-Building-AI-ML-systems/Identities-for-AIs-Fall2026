"""Fixed-probe onboarding, training and runtime regression tests (offline)."""
from __future__ import annotations
import json,shutil,tempfile,unittest
from pathlib import Path
from fingerprinting.onboarding import datasets as d,artifacts as a
from fingerprinting.training import orchestrator as o
from fingerprinting.training.random_forest import load_traces,fit_greedy
from fingerprinting.adapters import rf_panel_features as f
from fingerprinting.adapters.random_forest_panel import RandomForestPanelIdentifier
from fingerprinting.schemas import Observation,IdentificationInput
from fingerprinting.strategies import SingleMethodStrategy,ReplayTargetClient
ROOT=(Path(__file__).resolve().parents[2] / 'system')

class PanelTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.home=Path(tmp.name);self.root=self.home/'system';self.root.mkdir()
        shutil.copytree(ROOT/'catalog',self.root/'catalog');shutil.copytree(ROOT/'config',self.root/'config')
        (self.root/'models').mkdir();shutil.copyfile(ROOT/'models/registry.json',self.root/'models/registry.json')
        for rel in a.read_json(ROOT/'models/registry.json')['artifacts'].values():
            dst=self.root/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dst)
        self.raw=self.home/'raw';self.ids=['a','b'];self.models=['gemma3-4b','llama3.1-8b'];self.personas={name:[f'P{i}'] for i,name in enumerate(d.PARTITIONS)};self.dataset='collector_raw/panel';self.rows={}
        for m in self.models:
            self.rows[m]=[{'record_id':f'{m}-{p}-{j}-{q}','model_key':m,'prompt_id':q,'prompt_set_version':'fingerprint_v0','prompt_group':'probe','persona_id':p,'sample_index':j,'run_type':'library','deployment_id':None,'temperature':0.7,'max_tokens':1200,'response_text':('' if q=='a' and j==0 else 'hello gemma' if m==self.models[0] else 'llama model response'),'error':None} for ps in self.personas.values() for p in ps for j in range(2) for q in self.ids]
    def prepare(self,split=True):
        for m,rs in self.rows.items():
            path=self.raw/m/'fingerprint_v0.jsonl';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(''.join(json.dumps(r)+'\n' for r in rs))
        d.register(self.root,self.raw,'panel',source_note='test synthetic')
        if split:return self.split()
    def split(self):return d.split_fixed_panel(self.root,self.dataset,'p1',prompt_set='fingerprint_v0',probe_ids=self.ids,persona_partitions=self.personas)
    def test_persona_split_and_blank(self):
        result=self.prepare();self.assertEqual(result['algorithm'],d.PANEL_ALGORITHM)
        self.assertTrue(all(result['partitions'][p]['records']==8 for p in d.PARTITIONS))
        info=d.inspect_snapshot(self.root,self.dataset,'p1');self.assertEqual(info['probe_pool'],self.ids)
        p=self.home/'train.jsonl';d.export(self.root,self.dataset,'p1','train',p);tr=load_traces(p,self.ids,'fingerprint_v0');self.assertEqual(len(tr),4);self.assertEqual({t['persona_id'] for t in tr},{'P0'});self.assertEqual(sum(not t['answers']['a'] for t in tr),2)
    def test_retry_not_feature(self):
        self.rows[self.models[0]].append({**self.rows[self.models[0]][0],'record_id':'failed-retry','error':'timeout','response_text':None});r=self.prepare();self.assertEqual(r['partitions']['excluded']['records'],1)
    def test_unrecovered_error_fails(self):
        self.rows[self.models[0]][0]['error']='timeout';self.prepare(False)
        with self.assertRaises(d.DatasetError):self.split()
    def test_missing_probe_fails(self):
        self.rows[self.models[0]].pop();self.prepare(False)
        with self.assertRaises(d.DatasetError):self.split()
    def test_duplicate_success_fails(self):
        self.rows[self.models[0]].append({**self.rows[self.models[0]][0],'record_id':'duplicate-probe'});self.prepare(False)
        with self.assertRaisesRegex(d.DatasetError,'Duplicate probe'):self.split()
    def test_persona_leak_fails(self):
        self.personas['test'].append('P0');self.prepare(False)
        with self.assertRaisesRegex(d.DatasetError,'Persona crosses'):self.split()
    def test_tampered_assignment_fails(self):
        self.prepare();p=self.root/'datasets'/self.dataset/'splits/p1/test.jsonl';p.write_text('')
        with self.assertRaises(d.DatasetError):d.inspect_snapshot(self.root,self.dataset,'p1')
    def test_train_register_and_replay(self):
        self.prepare();aid='random_forest/test-panel';config={'dataset_id':self.dataset,'split_id':'p1','methods':{'random_forest':{'artifact_id':aid,'parameters':{'probe_budget':2,'n_estimators':5,'prompt_definitions':{'a':'A question','b':'B question'}}}}}
        report=o.run(self.root,config,o.available_trainers(),approve_dataset=True,register_candidates=True);self.assertEqual(report['status'],'completed',report)
        m=a.existing(self.root).get(aid);identifier=RandomForestPanelIdentifier(m);probes=identifier.required_probes();self.assertEqual(len(probes),2)
        observations={p.probe_id:Observation(p.prompt_text,'',prompt_id=p.probe_id,completed_blank=True) for p in probes};context=IdentificationInput(Observation('initial','initial'),probes={probes[0].probe_id:observations[probes[0].probe_id]})
        client=ReplayTargetClient(observations);result=SingleMethodStrategy(identifier).execute(context,client);self.assertEqual(len(client.asked),1);self.assertEqual(result.attempts[0].outcome,'unknown');self.assertIsNotNone(result.attempts[0].candidate_model_id);self.assertIsNone(result.accepted_model_id)
        with self.assertRaisesRegex(ValueError,'Missing RF probe'):identifier.identify(IdentificationInput(context.initial))
        bad=dict(observations);bad[probes[0].probe_id]=Observation('different text','some answer')
        with self.assertRaisesRegex(ValueError,'mismatch'):identifier.identify(IdentificationInput(context.initial,bad))
    def test_blank_is_explicit_not_failure(self):
        with self.assertRaises(ValueError):Observation('prompt','')
        self.assertEqual(Observation('prompt','',completed_blank=True).response_text,'')
        self.assertEqual(f.text_vector('')[f.FEATURES.index('blank_response')],1)
        self.assertEqual(f.text_vector('yes')[f.FEATURES.index('blank_response')],0)
        self.assertEqual(f.text_vector(None),f.text_vector(''))
    def test_order_independent_mapping(self):
        a1=f.frame([{'a':'alpha','b':'beta'}],['a','b']);a2=f.frame([{'b':'beta','a':'alpha'}],['a','b']);self.assertTrue(a1.equals(a2));self.assertEqual(list(a1.columns),f.columns(['a','b']))
    def test_greedy_disallows_persona_overlap(self):
        row={'model_id':'x','persona_id':'p','answers':{'a':'x'}};other={'model_id':'y','persona_id':'p','answers':{'a':'y'}}
        with self.assertRaisesRegex(ValueError,'Persona leakage'):fit_greedy([row,other],[row,other],['a'],budget=1,estimators=1)

if __name__=='__main__':unittest.main()
