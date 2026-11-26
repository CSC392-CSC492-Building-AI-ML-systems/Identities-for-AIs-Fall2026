"""Harness v2 reference-build, safety boundaries and worker replay."""
from __future__ import annotations
import ast,json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from fingerprinting.onboarding import datasets as d, artifacts as a
from fingerprinting.training import harness as h, orchestrator as o
from fingerprinting.adapters.harness import HarnessIdentifier
from fingerprinting.schemas import Observation,IdentificationInput
from fingerprinting.strategies import SingleMethodStrategy,ReplayTargetClient
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import PipelineFactory
from fingerprinting.adapters.builders import real_adapter_constructors
ROOT=(Path(__file__).resolve().parents[2] / 'system')

class HarnessReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=a.existing(ROOT);cls.manifest=cls.registry.get('harness/v2');cls.ref=cls.manifest.directory
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup);cls.paths={p:Path(cls.temp.name)/(p+'.jsonl') for p in ('train','validation')}
        cls.info=d.inspect_snapshot(ROOT,'collector_raw/agentic-2026-11-26','rf_panel_v1')
        for p,path in cls.paths.items():d.export(ROOT,'collector_raw/agentic-2026-11-26','rf_panel_v1',p,path)
    def test_coverage_and_pinned_reference_membership(self):
        rows,maps,devs,report=h.prepare_references(self.paths['train'],self.paths['validation'],self.info,self.registry.catalog)
        self.assertEqual(set(maps),self.registry.catalog.model_ids);self.assertEqual(report['reference_records'],816);self.assertEqual(report['blank_reference_records'],28)
        expected={r['record_id'] for rs in rows.values() for r in rs}
        actual={r['record_id'] for m in maps for _,r,_ in d.read_rows(self.ref/'collector/data/raw'/m/'fingerprint_v0.jsonl')}
        self.assertEqual(actual,expected);self.assertFalse(actual & {r['record_id'] for _,r,_ in d.read_rows(self.paths['validation'])});self.assertTrue(self.registry.readiness('harness/v2').ready)
        for rs in rows.values():self.assertTrue(all(r['sample_index'] in (0,1) for r in rs))
    def test_persona_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError,'Persona leakage'):h.prepare_references(self.paths['train'],self.paths['train'],self.info,self.registry.catalog)
    def test_wrong_protocol_and_provider(self):
        self.assertFalse(h.HarnessTrainer().supports({'split_algorithm':d.ALGORITHM}));self.assertTrue(h.HarnessTrainer().supports(self.info))
        with self.assertRaises(ValueError):h.parameters({'judge_provider':'anthropic'})
        with self.assertRaises(ValueError):h.parameters({'activate':True})
    def test_review_only_even_high_fit_and_no_legacy_deployment(self):
        def runner(payload):
            self.assertIsNone(payload['deployment']);self.assertEqual(len(payload['answers']),6);self.assertEqual(payload['answers']['I1'],'')
            return {'identified':{'model_key':'llama3.2-1b'},'fit_score':1,'status':'Identified','handoff_to_next_method':False,'card':{'unsafe':'candidate'},'reasons':[]}
        ident=HarnessIdentifier(self.manifest,judge_provider='google',runner=runner)
        obs={p.probe_id:Observation(p.prompt_text,'' if p.probe_id=='I1' else 'test',p.probe_id,completed_blank=p.probe_id=='I1') for p in ident.required_probes()}
        r=ident.identify(IdentificationInput(Observation('initial','text'),probes=obs,deployment_id='owned-deployment'))
        self.assertEqual(r.candidate_model_id,'llama3.2-1b');self.assertIsNone(r.accepted_model_id);self.assertTrue(r.handoff_requested);self.assertNotIn('card',r.diagnostics)
    def test_real_worker_mock_all_blank(self):
        ident=HarnessIdentifier(self.manifest,judge_provider='mock');obs={p.probe_id:Observation(p.prompt_text,'',p.probe_id,completed_blank=True) for p in ident.required_probes()}
        result=SingleMethodStrategy(ident).execute(IdentificationInput(Observation('initial','text')),ReplayTargetClient(obs))
        self.assertEqual(result.attempts[0].outcome,'unknown');self.assertIsNone(result.accepted_model_id);self.assertTrue(result.attempts[0].handoff_requested)
    def test_actual_source_profile_and_blank_rule(self):
        # Test the emitted upstream modules in their own interpreter, no imports
        # or module cache collisions with v1.
        code='''from identify import MODELS,load_records\nfrom probe_identify import profile,code_misfits\nr=load_records(MODELS,['fingerprint'])\nassert len(MODELS)==17 and len(r)==816 and sum(not a['response_text'].strip() for a in r)==28\nassert 'blank 100%' in profile(['']*4)\nassert code_misfits({'p':''},{'p':['']*4})==[]\nassert code_misfits({'p':'hello'},{'p':['']*4})==['p: blank']\n'''
        p=subprocess.run([sys.executable,'-B','-c',code],cwd=self.ref/'agent',capture_output=True,text=True,timeout=20);self.assertEqual(p.returncode,0,p.stderr)
    def test_factory_off_stage1_and_no_cards_copy(self):
        cfg=load_pipeline_config(ROOT/'config/experiments/harness_v2.yaml',self.registry)
        self.assertFalse(cfg.stage1.enabled);self.assertFalse((self.ref/'cards').exists())
        strat=PipelineFactory(self.registry,real_adapter_constructors(harness_judge_provider='mock')).build_stage2(cfg)
        self.assertEqual(strat.identifiers[0].artifact_id,'harness/v2')
    def test_duplicate_refresh_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=o.TrainingContext('harness','harness/test-refresh','collector_raw/agentic-2026-11-26','rf_panel_v1',self.info['dataset_manifest_sha256'],self.info['split_manifest_sha256'],self.info['eligibility_policy'],self.paths['train'],self.paths['validation'],Path(tmp),{},self.info['split_algorithm'],self.info['probe_pool'],self.info['prompt_set_version'],ROOT)
            with self.assertRaises(o.UnchangedCandidate) as cm:h.HarnessTrainer().run(ctx)
            self.assertEqual(cm.exception.artifact_ids,['harness/v2']);self.assertEqual(list(Path(tmp).iterdir()),[])
    def test_deferred_stage1_plan(self):
        cfg={'dataset_id':'collector_raw/agentic-2026-11-26','split_id':'rf_panel_v1','methods':{'logistic_regression':{'artifact_id':'stage1_lr/test-deferred','parameters':{}}}}
        self.assertEqual(o.plan(ROOT,cfg,o.available_trainers())['methods']['logistic_regression']['status'],'blocked_stage1_deferred')
    def test_no_legacy_artifact_changed(self):
        self.assertTrue(self.registry.readiness('harness/v1').ready)
        self.assertEqual(len(self.registry.get('harness/v1').supported_models),11)

if __name__=='__main__':unittest.main()
