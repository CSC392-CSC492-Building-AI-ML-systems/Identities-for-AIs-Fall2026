"""LoRA contract and routing tests; synthetic probabilities, no network or GPU required."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from fingerprinting.adapters.lora import LoRAConfigurationError, LoRAIdentifier, build_lora
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, FactoryError, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import IdentificationInput, IdentificationResult, Observation
from fingerprinting.strategies import FallbackStrategy, SingleMethodStrategy
from fingerprinting.testing import StubIdentifier

ROOT = (Path(__file__).resolve().parents[2] / 'system')


class LoRAAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ArtifactRegistry(ROOT, ModelCatalog.from_file(ROOT / 'catalog/models.json'))
        cls.manifest = cls.registry.get('lora/v1')
        cls.cfg = load_pipeline_config(ROOT / 'config/experiments/lora_only.yaml', cls.registry)

    def identifier(self, probs=(.05, .75, .1, .08, .02), manifest=None):
        return LoRAIdentifier(manifest or self.manifest, predictor=lambda _: probs)

    @staticmethod
    def context():
        return IdentificationInput(initial=Observation('Give me a definition', 'A definition is ...'))

    def test_v1_labels_and_input_contract(self):
        a = self.identifier()
        self.assertEqual(a.required_probes(), ())
        self.assertEqual(a.labels, ('gemma3-4b', 'llama3.1-8b', 'llama3.2-3b', 'qwen3-8b', 'qwen3.5-9b'))
        self.assertEqual(a.name, 'lora')

    def test_review_only_prediction_requests_handoff(self):
        r = self.identifier().identify(self.context())
        self.assertEqual(r.candidate_model_id, 'llama3.1-8b')
        self.assertEqual(r.outcome, 'unknown')
        self.assertTrue(r.handoff_requested)
        self.assertIsNone(r.accepted_model_id)
        self.assertEqual(r.score_type, 'max_softmax')
        self.assertEqual(set(r.model_scores), set(self.manifest.supported_models))

    def test_normalization_and_class_count_checked(self):
        for invalid in ((0.1,), (.5, .5, .3, 0, 0), (.5, -.1, .6, 0, 0),
                        (float('nan'), .5, .5, 0, 0)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.identifier(invalid).identify(self.context())

    def test_label_order_mismatch_rejected(self):
        wrong = replace(self.manifest, options={**self.manifest.options, 'label_order': ['llama3.1-8b']})
        with self.assertRaises(LoRAConfigurationError):
            self.identifier(manifest=wrong)

    def test_validated_policy_requires_grounded_validation(self):
        wrong = replace(self.manifest, options={**self.manifest.options,
                        'acceptance_policy': {'mode':'validated_threshold','threshold': 0.8}})
        with self.assertRaises(LoRAConfigurationError):
            self.identifier(manifest=wrong)

    def test_validated_threshold_branch(self):
        opts = {**self.manifest.options, 'acceptance_policy': {
            'mode': 'validated_threshold', 'threshold': 0.7,
            'validation_id': 'synthetic-unit-test-only', 'includes_unknown_models': True}}
        selected = self.identifier(manifest=replace(self.manifest, options=opts))
        r = selected.identify(self.context())
        self.assertEqual(r.outcome, 'identified')
        self.assertEqual(r.accepted_model_id, 'llama3.1-8b')
        self.assertFalse(r.handoff_requested)
        low = self.identifier((.05, .60, .20, .10, .05), manifest=replace(self.manifest, options=opts))
        self.assertEqual(low.identify(self.context()).outcome, 'unknown')

    def test_fallback_starts_with_lora_then_mock_harness(self):
        lora = self.identifier()
        harness = StubIdentifier('harness', IdentificationResult('harness', 'identified',
                                    candidate_model_id='llama3.2-3b', accepted_model_id='llama3.2-3b'))
        res = FallbackStrategy((lora, harness)).execute(self.context())
        self.assertEqual([a.method for a in res.attempts], ['lora', 'harness'])
        self.assertEqual(res.accepted_model_id, 'llama3.2-3b')

    def test_factory_build_stage2_only_uses_selected_artifacts(self):
        constructors = AdapterConstructors()
        constructors.register_stage2('lora', lambda m, s: self.identifier(manifest=m))
        stage2 = PipelineFactory(self.registry, constructors, require_ready=False).build_stage2(self.cfg)
        self.assertIsInstance(stage2, SingleMethodStrategy)
        res = stage2.execute(self.context())
        self.assertIsNone(res.attempts[0].candidate_model_id)
        self.assertEqual(res.attempts[0].diagnostics['raw_class_probabilities'],[.05,.75,.1,.08,.02])

    def test_factory_real_lora_readiness_fails_before_constructor(self):
        constructors = AdapterConstructors()
        called = []
        constructors.register_stage2('lora', lambda m, s: called.append(True))
        # Historical v1 is intentionally incomplete; production now selects v2.
        from fingerprinting.eval_suite import with_stage2
        from fingerprinting.config import Stage2MethodSelection
        old_cfg = with_stage2(self.cfg, [Stage2MethodSelection('lora', 'lora/v1')], 'single')
        with self.assertRaisesRegex(FactoryError, 'not ready'):
            PipelineFactory(self.registry, constructors).build_stage2(old_cfg)
        self.assertFalse(called)

    def test_real_loader_missing_base_revision_fails_before_network(self):
        a = LoRAIdentifier(self.manifest)
        with self.assertRaisesRegex(LoRAConfigurationError, 'base_model_revision'):
            a.identify(self.context())

    def test_builder_validates_selection(self):
        self.assertEqual(build_lora(self.registry.get('lora/v2'), self.cfg.stage2.methods[0]).name, 'lora')


if __name__ == '__main__':
    unittest.main()

class LoRAIndependentEvaluationTests(unittest.TestCase):
    def test_candidate_accuracy_is_measured_even_when_not_accepted(self):
        from fingerprinting.evaluation import EvaluationRunner
        from fingerprinting.schemas import EvaluationCase, FingerprintRequest
        root = (Path(__file__).resolve().parents[2] / 'system')
        reg = ArtifactRegistry(root, ModelCatalog.from_file(root / 'catalog/models.json'))
        manifest = reg.get('lora/v1')
        adapter = LoRAIdentifier(manifest, predictor=lambda t: (.05,.75,.10,.08,.02))
        obs = Observation('Prompt', 'Response')
        req = FingerprintRequest('example',obs, 'llama3.1-8b','llama')
        case = EvaluationCase('case',req, 'llama3.1-8b','llama','synthetic','test')
        report = EvaluationRunner.stage2([case], SingleMethodStrategy(adapter))
        self.assertEqual(report.metrics['accepted'], 0)
        self.assertEqual(report.metrics['by_method']['lora']['candidate_top1_accuracy'], 1.0)
        self.assertEqual(report.metrics['by_method']['lora']['candidate_predictions'], 1)

class LoRAWithRealStage1Tests(unittest.TestCase):
    def test_actual_stage1_routes_to_mock_score_lora(self):
        """Tests pipeline composition, not the LoRA-trained weights."""
        import warnings
        from fingerprinting.adapters.logistic_regression import build_logistic_regression
        from fingerprinting.pipeline import FingerprintPipeline
        from fingerprinting.schemas import FingerprintRequest

        reg = ArtifactRegistry(ROOT, ModelCatalog.from_file(ROOT / 'catalog/models.json'))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            verifier = build_logistic_regression(reg.get('stage1_lr/v1'),
                         type('Selected', (), {'approach': 'hierarchy_hard_route'})())
        lora = LoRAIdentifier(reg.get('lora/v1'), predictor=lambda _: (.05, .75, .1, .08, .02))
        pipeline = FingerprintPipeline(verifier, SingleMethodStrategy(lora))
        req = FingerprintRequest('case-real-stage1', Observation('Who made you?',
                   'I am Gemini, a large language model developed by Google.'),
                   'gemini-3.1-pro', 'gemini')
        result = pipeline.run(req)
        self.assertEqual(result.stage1.verdict, 'mismatch')
        self.assertEqual(result.final.status, 'needs_review')
        self.assertEqual([a.method for a in result.stage2_attempts], ['lora'])
        self.assertEqual(result.stage2_attempts[0].candidate_model_id, 'llama3.1-8b')
        self.assertIsNone(result.stage2_attempts[0].accepted_model_id)
