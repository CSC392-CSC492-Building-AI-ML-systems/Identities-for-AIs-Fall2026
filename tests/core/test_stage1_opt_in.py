"""Stage 1 is opt-in; Stage 2 defaults on. No real ML or external calls."""
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace

from fingerprinting.config import load_pipeline_config, check_config_readiness
from fingerprinting.eval_suite import run_suite, with_stage1_enabled
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.pipeline import FingerprintPipeline
from fingerprinting.schemas import (EvaluationCase, FingerprintRequest, IdentificationResult,
                                    Observation, Stage1Result)
from fingerprinting.strategies import SingleMethodStrategy
from fingerprinting.testing import StubIdentifier, StubStage1

ROOT = (Path(__file__).resolve().parents[2] / 'system')


def make_request(with_expected=False):
    args = ('llama3.1-8b', 'llama') if with_expected else (None, None)
    return FingerprintRequest('request-new', Observation('What is recursion?', 'A recursive function calls itself.', 'P-001'), *args)


class Stage1OptInTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')
        cls.registry = ArtifactRegistry(ROOT, cls.catalog)
        cls.config = load_pipeline_config(ROOT/'config/experiments/random_forest_only.yaml', cls.registry)

    def make_builders(self, calls):
        constructors = AdapterConstructors()
        def stage1_builder(manifest, selection):
            calls.append(('stage1_construct', selection.approach))
            class Verifier:
                name = 'test_stage1'
                def verify(self, request):
                    calls.append(('stage1_verify', request.request_id))
                    return Stage1Result('verified', family_match=True, model_match=True)
            return Verifier()
        def stage2_builder(manifest, selection):
            calls.append(('stage2_construct', selection.adapter))
            class Identifier:
                name = 'random_forest'
                def required_probes(self):
                    return ()
                def identify(self, context):
                    calls.append(('stage2_identify', context.initial.prompt_id))
                    return IdentificationResult('random_forest', 'identified',
                                                'llama3.2-3b', 'llama3.2-3b')
            return Identifier()
        constructors.register_stage1('logistic_regression', stage1_builder)
        constructors.register_stage2('random_forest', stage2_builder)
        return constructors

    def factory_pipeline(self, calls):
        return PipelineFactory(self.registry, self.make_builders(calls),
                               require_ready=False).build(self.config)

    def test_default_config_disables_stage1(self):
        self.assertFalse(self.config.stage1.enabled)
        self.assertFalse(load_pipeline_config(ROOT/'config/production.yaml', self.registry).stage1.enabled)
        self.assertNotIn('stage1_lr/v1', check_config_readiness(self.config, self.registry)['artifacts'])

    def test_default_stage2_no_expected_model(self):
        calls = []
        p = self.factory_pipeline(calls)
        self.assertEqual(calls, [('stage2_construct', 'random_forest')])
        result = p.run(make_request())
        self.assertEqual(result.final.status, 'identified')
        self.assertEqual(result.final.model_id, 'llama3.2-3b')
        self.assertFalse(result.stage1_enabled)
        self.assertEqual(result.stage1.verdict, 'skipped')
        self.assertIsNone(result.stage1_strategy)
        self.assertEqual(result.routing_trace[0], 'stage1:skipped')
        self.assertNotIn('stage1_construct', [x[0] for x in calls])
        json.dumps(result.to_dict())

    def test_expected_model_given_without_stage1(self):
        calls = []
        p = self.factory_pipeline(calls)
        result = p.run(make_request(with_expected=True))
        self.assertEqual(result.final.status, 'drift_detected')
        self.assertFalse(result.stage1_enabled)
        self.assertEqual(result.final.resolved_by, 'random_forest')

    def test_opt_in_is_lazy_cached_and_per_request(self):
        calls = []
        p = self.factory_pipeline(calls)
        req = make_request(with_expected=True)
        checked = p.run(req, use_stage1=True)
        self.assertTrue(checked.stage1_enabled)
        self.assertEqual(checked.final.resolved_by, 'stage1')
        self.assertEqual(checked.stage2_attempts, [])
        self.assertEqual(len([x for x in calls if x[0] == 'stage1_construct']), 1)
        p.run(req, use_stage1=True)
        self.assertEqual(len([x for x in calls if x[0] == 'stage1_construct']), 1)
        default = p.run(req)
        self.assertFalse(default.stage1_enabled)
        self.assertEqual(default.final.resolved_by, 'random_forest')

    def test_missing_expected_when_enabled_fails_before_load(self):
        calls = []
        p = self.factory_pipeline(calls)
        with self.assertRaisesRegex(ValueError, 'requires expected_model_id'):
            p.run(make_request(), use_stage1=True)
        self.assertEqual(calls, [('stage2_construct', 'random_forest')])

    def test_no_stage1_constructor_needed_until_opt_in(self):
        calls = []
        constructors = self.make_builders(calls)
        constructors.stage1.clear()
        p = PipelineFactory(self.registry, constructors, require_ready=False).build(self.config)
        self.assertEqual(p.run(make_request()).stage1.verdict, 'skipped')
        with self.assertRaisesRegex(ValueError, 'No Stage 1 builder'):
            p.run(make_request(with_expected=True), use_stage1=True)

    def test_explicit_config_true_eager_stage1(self):
        calls = []
        cfg = with_stage1_enabled(self.config, True)
        p = PipelineFactory(self.registry, self.make_builders(calls),
                            require_ready=False).build(cfg)
        self.assertEqual(calls[0][0], 'stage1_construct')
        self.assertTrue(p.run(make_request(with_expected=True)).stage1_enabled)
        self.assertFalse(p.run(make_request(), use_stage1=False).stage1_enabled)

    def test_independent_evaluation_unaffected(self):
        calls = []
        p = self.factory_pipeline(calls)
        req = make_request(with_expected=True)
        case = EvaluationCase('request-new', req, 'llama3.2-3b', 'llama', 'fixture', 'test')
        s2 = EvaluationRunner.e2e([case], p)
        self.assertEqual(s2.metrics['stage1_invocations'], 0)
        self.assertEqual(s2.metrics['drift_detected'], 1)
        checked = EvaluationRunner.e2e([case],
            PipelineFactory(self.registry, self.make_builders([]), require_ready=False).build(
                with_stage1_enabled(self.config, True)))
        self.assertEqual(checked.metrics['stage1_invocations'], 1)
        self.assertEqual(checked.metrics['false_verification_count'], 1)

    def test_unnamed_identification_does_not_claim_drift(self):
        p = self.factory_pipeline([])
        case = EvaluationCase('request-new', make_request(), 'llama3.2-3b', 'llama', 'fixture', 'test')
        report = EvaluationRunner.e2e([case], p)
        self.assertEqual(report.metrics['identified'], 1)
        self.assertEqual(report.metrics['without_expected_model'], 1)
        self.assertEqual(report.metrics['true_drift_cases'], 0)
        self.assertIsNone(report.metrics['drift_detection_recall'])

    def test_suite_e2e_respects_opt_in(self):
        req = make_request(with_expected=True)
        case = EvaluationCase('request-new', req, 'llama3.2-3b', 'llama', 'fixture', 'test')
        factory = PipelineFactory(self.registry, self.make_builders([]), require_ready=False)
        off = run_suite([case], self.config, self.registry, factory, scope='e2e',
                        methods=['random_forest'])
        on = run_suite([case], self.config, self.registry, factory, scope='e2e',
                       methods=['random_forest'], use_stage1=True)
        self.assertFalse(off['requested']['use_stage1'])
        self.assertTrue(on['requested']['use_stage1'])
        self.assertEqual(off['reports']['e2e']['metrics']['stage1_invocations'], 0)
        self.assertEqual(on['reports']['e2e']['metrics']['stage1_invocations'], 1)

    def test_stage1_inactive_is_not_a_readiness_dependency(self):
        cfg = self.config
        only_stage2 = check_config_readiness(cfg, self.registry)
        explicit_stage1 = check_config_readiness(cfg, self.registry, include_stage1=True)
        self.assertTrue(only_stage2['ready'])
        self.assertIn('stage1_lr/v1', explicit_stage1['artifacts'])
        self.assertNotIn('stage1_lr/v1', only_stage2['artifacts'])

    def test_config_stage1_enabled_type_validation(self):
        from fingerprinting.config import ConfigurationError
        text = (ROOT/'config/production.yaml').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'bad.yaml'
            path.write_text(text.replace('enabled: false', 'enabled: "false"', 1))
            with self.assertRaisesRegex(ConfigurationError, 'stage1.enabled'):
                load_pipeline_config(path, self.registry)


if __name__ == '__main__':
    unittest.main()
