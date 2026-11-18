"""Harness v1 integration tests; no external judge API requests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fingerprinting.adapters.harness import HarnessIdentifier, HarnessExecutionError
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import (EvaluationCase, IdentificationResult, FingerprintRequest, IdentificationInput,
                                    Observation, Stage1Result)
from fingerprinting.strategies import ReplayTargetClient, SingleMethodStrategy, FallbackStrategy
from fingerprinting.testing import StubStage1

ROOT = Path(__file__).resolve().parents[1]


def known_result(*, model_key='llama3.1-8b', handoff=False, status='Identified', fit=0.9):
    return {'identified': {'developer': 'Meta', 'family': 'Llama', 'version': 'Llama 3.1 8B',
                           'model_key': model_key, 'closest_known_version': None},
            'status': status, 'handoff_to_next_method': handoff, 'fit_score': fit,
            'reasons': ['Unit fixture'], 'judge': {'version': 'Llama 3.1 8B'}}


class HarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ArtifactRegistry(ROOT, ModelCatalog.from_file(ROOT/'catalog/models.json'))
        cls.manifest = cls.registry.get('harness/v1')

    def identifier(self, response=None, provider='google'):
        return HarnessIdentifier(self.manifest, judge_provider=provider,
                                 runner=(lambda _: response or known_result()))

    def context(self, identifier, *, missing=False, domain='risk', deployment=None):
        probes = identifier.required_probes()
        probes = probes[:-1] if missing else probes
        return IdentificationInput(
            initial=Observation('Initial user prompt','Some initial response'),
            probes={p.probe_id: Observation(p.prompt_text, 'I am Llama 3.1 by Meta.', p.probe_id)
                    for p in probes}, domain=domain, deployment_id=deployment)

    def test_six_versioned_probes(self):
        h = self.identifier()
        self.assertEqual([p.probe_id for p in h.required_probes()],
                         ['LM-01', 'LM-05', 'LM-06', 'I1', 'I2', 'V1-15'])
        self.assertTrue(all(p.prompt_text.strip() for p in h.required_probes()))

    def test_ready_artifact(self):
        r = self.registry.readiness('harness/v1')
        self.assertTrue(r.ready, r)
        self.assertGreaterEqual(len(self.manifest.required_files), 60)

    def test_legacy_acceptance_mapping(self):
        h = self.identifier()
        result = h.identify(self.context(h))
        self.assertEqual(result.accepted_model_id, 'llama3.1-8b')
        self.assertEqual(result.method, 'harness')
        self.assertEqual(result.score_type, 'fit_score')
        self.assertEqual(result.score, .9)
        self.assertFalse(result.handoff_requested)
        self.assertEqual(len(result.probe_ids_used), 6)

    def test_handoff_is_not_accepted(self):
        h = self.identifier(known_result(handoff=True))
        result = h.identify(self.context(h))
        self.assertEqual(result.outcome, 'unknown')
        self.assertEqual(result.candidate_model_id, 'llama3.1-8b')
        self.assertIsNone(result.accepted_model_id)
        self.assertTrue(result.handoff_requested)

    def test_needs_review_is_not_accepted(self):
        h = self.identifier(known_result(status='Needs review'))
        self.assertIsNone(h.identify(self.context(h)).accepted_model_id)

    def test_mock_judge_is_never_accepted(self):
        h = self.identifier(provider='mock')
        result = h.identify(self.context(h))
        self.assertIsNone(result.accepted_model_id)
        self.assertTrue(result.diagnostics['mock_judge'])

    def test_missing_answers_error(self):
        h = self.identifier()
        with self.assertRaisesRegex(ValueError, 'Missing Harness probe'):
            h.identify(self.context(h,missing=True))

    def test_mismatched_prompt_text_rejected(self):
        h = self.identifier()
        ctx=self.context(h)
        x=dict(ctx.probes)
        p=h.required_probes()[0]
        x[p.probe_id] = Observation('Different prompt', 'response', p.probe_id)
        with self.assertRaisesRegex(ValueError, 'different prompt text'):
            h.identify(IdentificationInput(ctx.initial,x))

    def test_invalid_deployment_id_rejected(self):
        h=self.identifier()
        with self.assertRaisesRegex(ValueError,'deployment_id'):
            h.identify(self.context(h,deployment='../not-valid'))

    def test_unknown_model_id_rejected(self):
        h=self.identifier(known_result(model_key='not-a-known-model'))
        with self.assertRaises(HarnessExecutionError):
            h.identify(self.context(h))

    def test_invalid_fit_rejected(self):
        h=self.identifier(known_result(fit=1.2))
        with self.assertRaises(HarnessExecutionError):
            h.identify(self.context(h))

    def test_probe_replay_collection_uses_exact_prompts(self):
        h=self.identifier()
        source=self.context(h)
        client=ReplayTargetClient(source.probes)
        run=SingleMethodStrategy(h).execute(IdentificationInput(source.initial,domain='risk'),client)
        self.assertEqual(len(client.asked),6)
        self.assertEqual(len(run.probe_ids_collected),6)
        self.assertEqual(run.accepted_model_id,'llama3.1-8b')

    def test_factory_constructs_standalone_real_harness(self):
        config=load_pipeline_config(ROOT/'config/experiments/harness_only.yaml',self.registry)
        constructors=AdapterConstructors()
        constructors.register_stage2('harness',lambda m,s: HarnessIdentifier(m, judge_provider='mock'))
        stage2=PipelineFactory(self.registry,constructors).build_stage2(config)
        self.assertEqual(stage2.identifiers[0].name,'harness')
        self.assertEqual(len(stage2.identifiers[0].required_probes()),6)

    def test_full_pipeline_stage1_mismatch_to_harness(self):
        config=load_pipeline_config(ROOT/'config/experiments/harness_only.yaml',self.registry)
        constructors=AdapterConstructors()
        constructors.register_stage1('logistic_regression',lambda m,s: StubStage1('mismatch',
            Stage1Result('mismatch',family_match=False,model_match=None)))
        constructors.register_stage2('harness',lambda m,s: HarnessIdentifier(m,
            runner=lambda _:known_result()))
        pipeline=PipelineFactory(self.registry,constructors).build(config)
        h=pipeline.stage2.identifiers[0]
        context=self.context(h)
        req=FingerprintRequest('case1',context.initial,'llama3.2-3b','llama',domain='risk')
        outcome=pipeline.run(req, ReplayTargetClient(context.probes))
        self.assertEqual(outcome.final.resolved_by,'harness')
        self.assertEqual(outcome.final.status,'drift_detected')
        self.assertEqual(outcome.artifact_ids['harness'],'harness/v1')

    def test_lora_review_then_harness_fallback(self):
        from fingerprinting.testing import StubIdentifier
        from fingerprinting.pipeline import FingerprintPipeline
        lora = StubIdentifier('lora', IdentificationResult('lora', 'unknown',
                                 candidate_model_id='llama3.1-8b',
                                 handoff_requested=True))
        h = self.identifier()
        context = self.context(h)
        stage1 = StubStage1('mismatch', Stage1Result('mismatch', family_match=False))
        pipeline = FingerprintPipeline(stage1, FallbackStrategy([lora, h]))
        req = FingerprintRequest('fallthrough', context.initial, 'llama3.2-3b', 'llama')
        out = pipeline.run(req, ReplayTargetClient(context.probes))
        self.assertEqual([x.method for x in out.stage2_attempts], ['lora', 'harness'])
        self.assertEqual(out.final.resolved_by, 'harness')
        self.assertEqual(out.final.status, 'drift_detected')

    def test_independent_evaluator_harness_replay(self):
        from fingerprinting.evaluation import EvaluationRunner
        h = self.identifier()
        ctx = self.context(h)
        case = EvaluationCase(
            'test-1', FingerprintRequest('test-1', ctx.initial, 'llama3.2-3b', 'llama'),
            'llama3.1-8b', 'llama', 'synthetic', 'test', replay_probes=ctx.probes)
        report = EvaluationRunner.stage2([case], SingleMethodStrategy(h))
        self.assertEqual(report.metrics['accepted_exact_model_accuracy'], 1.0) if 'accepted_exact_model_accuracy' in report.metrics else self.assertTrue(report.rows[0]['exact_match'])
        self.assertEqual(report.rows[0]['selected_method'], 'harness')

    def test_real_legacy_worker_mock_no_network(self):
        # This executes the ORIGINAL Harness code, including reference loading,
        # code rules and card lookup. Only the judge LLM is replaced by its mock.
        h=HarnessIdentifier(self.manifest,judge_provider='mock')
        probe_map=json.loads((ROOT/'testdata/harness_replay/llama3.1-8b_BK1_sample2.json').read_text())
        context=IdentificationInput(
            initial=Observation('Original prompt','Original response'),
            probes={p.probe_id:Observation(p.prompt_text,probe_map[p.probe_id],p.probe_id)
                    for p in h.required_probes()}, domain='risk')
        result=h.identify(context)
        self.assertEqual(result.method,'harness')
        self.assertEqual(result.diagnostics['mock_judge'],True)
        self.assertIsNone(result.accepted_model_id)
        self.assertIn(result.diagnostics['legacy_status'],('Identified','Unknown model'))
        self.assertEqual(result.diagnostics['card']['domains'][0]['domain'],'risk')


if __name__ == '__main__':
    unittest.main()
