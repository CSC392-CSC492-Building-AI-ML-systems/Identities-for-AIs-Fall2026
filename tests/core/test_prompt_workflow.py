"""Prompt-first UI handoff tests. All providers, cards and models are synthetic."""
import unittest
from pathlib import Path
from fingerprinting.clients import CallableTargetClient
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.pipeline import FingerprintPipeline
from fingerprinting.schemas import IdentificationInput, IdentificationResult, ProbeQuestion, Stage1Result
from fingerprinting.strategies import FallbackStrategy, SingleMethodStrategy
from fingerprinting.workflow import BaselineSnapshot, PromptAnalysisService

ROOT = (Path(__file__).resolve().parents[2] / 'system')


class TestPromptWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')

    def make_pipeline(self, candidate='llama3.2-3b', accepted=True, probes=()):
        class Identifier:
            name='harness'
            def required_probes(self): return probes
            def identify(self, context):
                for p in probes: self_ignored = context.probes[p.probe_id]
                return IdentificationResult('harness', 'identified' if accepted else 'unknown',
                    candidate_model_id=candidate, accepted_model_id=candidate if accepted else None)
        return FingerprintPipeline(None, SingleMethodStrategy(Identifier()), stage1_enabled=False)

    def test_one_prompt_then_six_probes_and_card(self):
        questions = tuple(ProbeQuestion(f'P{i}', f'Probe {i}') for i in range(6))
        calls=[]
        def fake(prompt):
            calls.append(prompt)
            return 'Synthetic reply for '+prompt
        class Cards:
            def resolve(self, model_id, domain=None):
                return {'model_id':model_id, 'risk':'medium', 'domain':domain}
        service=PromptAnalysisService(self.make_pipeline(probes=questions),self.catalog,card_resolver=Cards())
        report=service.analyze('What is recursion?',CallableTargetClient(fake),request_id='flow-1',domain='risk')
        self.assertEqual(calls,['What is recursion?']+[f'Probe {i}' for i in range(6)])
        self.assertEqual(report.target_queries,['UI-INITIAL']+[f'P{i}' for i in range(6)])
        self.assertEqual(report.current_model_id,'llama3.2-3b')
        self.assertEqual(report.model_card_status,'available')
        self.assertEqual(report.change_status,'no_baseline')
        self.assertEqual(report.fingerprint.stage1.verdict,'skipped')
        self.assertNotIn('api_key',str(report.to_dict()).lower())

    def test_baseline_model_change_and_card_changes(self):
        class Cards:
            def resolve(self, model_id, domain=None):return {'risk':'high','license':'new'}
        svc=PromptAnalysisService(self.make_pipeline(),self.catalog,card_resolver=Cards())
        report=svc.analyze('Question', CallableTargetClient(lambda _: 'Reply'),request_id='flow-2',
            baseline=BaselineSnapshot('llama3.1-8b',{'risk':'low','license':'old'}))
        self.assertEqual(report.change_status,'model_changed')
        self.assertEqual(report.fingerprint.final.status,'drift_detected')
        self.assertEqual(report.card_comparison_status,'compared')
        self.assertEqual({x['field'] for x in report.card_changes},{'risk','license'})

    def test_same_model_no_change(self):
        svc=PromptAnalysisService(self.make_pipeline('llama3.2-3b'),self.catalog)
        out=svc.analyze('Hi',CallableTargetClient(lambda _:'Hello'),request_id='flow-3',
            baseline=BaselineSnapshot('llama3.2-3b'))
        self.assertEqual(out.change_status,'same_model')
        self.assertEqual(out.model_card_status,'unavailable')
        self.assertEqual(out.card_comparison_status,'not_comparable')

    def test_candidate_not_claimed_as_identified(self):
        svc=PromptAnalysisService(self.make_pipeline(accepted=False),self.catalog)
        out=svc.analyze('Hi',CallableTargetClient(lambda _:'Hello'),request_id='flow-4',
            baseline=BaselineSnapshot('llama3.1-8b'))
        self.assertIsNone(out.current_model_id)
        self.assertEqual(out.change_status,'unresolved')
        self.assertEqual(out.model_card_status,'unconfirmed')
        self.assertEqual(out.fingerprint.stage2_attempts[0].candidate_model_id,'llama3.2-3b')

    def test_stage1_validation_before_target_api_call(self):
        n=[]
        svc=PromptAnalysisService(self.make_pipeline(),self.catalog)
        with self.assertRaisesRegex(ValueError,'Stage 1 requires'):
            svc.analyze('Hi',CallableTargetClient(lambda text:n.append(text) or 'x'),
                        request_id='x',use_stage1=True)
        self.assertEqual(n,[])
        with self.assertRaisesRegex(ValueError,'Unknown canonical'):
            svc.analyze('Hi',CallableTargetClient(lambda text:n.append(text) or 'x'),
                        request_id='x',use_stage1=True,baseline=BaselineSnapshot('unknown-model'))
        self.assertEqual(n,[])

    def test_no_prompt_response_required_from_ui(self):
        svc=PromptAnalysisService(self.make_pipeline(),self.catalog)
        with self.assertRaisesRegex(ValueError,'prompt'):
            svc.analyze(' ', CallableTargetClient(lambda _:'Hello'), request_id='fail')

    def test_wrong_response_prompt_rejected(self):
        from fingerprinting.schemas import Observation
        class BrokenClient:
            def ask(self, probe):return Observation('another prompt','Some response')
        svc=PromptAnalysisService(self.make_pipeline(),self.catalog)
        with self.assertRaisesRegex(ValueError,'different prompt'):
            svc.analyze('Hi',BrokenClient(),request_id='fail')


if __name__=='__main__':unittest.main()
