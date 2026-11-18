"""Real Stage 1 integration tests. Loads only user-provided, checksummed artifacts.

The original script is retained under reference_stage1/ for independent parity
checks. There is NO stage 2 model loading or API use in these tests.
"""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
import warnings
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

from fingerprinting.adapters.logistic_regression import build_logistic_regression
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, FactoryError, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import FingerprintRequest, Observation

ROOT = Path(__file__).resolve().parents[1]
TEXTS = (
    'I am Gemini, a large language model developed by Google.',
    'I am an AI assistant developed by Meta. I can help with coding, reasoning and research.',
    'Here are three ways to approach it: consider your goals and then compare options.',
)
TARGETS = ('gemini-3.1-pro', 'gemini-3.8-flash', 'llama3.1-8b', 'llama3.2-3b')
FAMILIES = {'gemini-3.1-pro': 'gemini', 'gemini-3.8-flash': 'gemini',
            'llama3.1-8b': 'llama', 'llama3.2-3b': 'llama'}


class RealStage1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ModelCatalog.from_file(ROOT / 'catalog/models.json')
        cls.registry = ArtifactRegistry(ROOT, cls.catalog)
        cls.manifest = cls.registry.get('stage1_lr/v1')
        cls.verifiers = {}
        # Avoid testing warnings about scikit-learn 1.6.1 -> 1.8.0 as errors.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for approach in ('hierarchy_hard_route', 'hierarchy_soft', 'ovr_direct'):
                cls.verifiers[approach] = build_logistic_regression(cls.manifest,
                    type('Selection', (), {'approach': approach})())

    @staticmethod
    def request(target, response, request_id='real-001'):
        return FingerprintRequest(request_id,
            Observation('Who developed you?', response, 'stage1-real'), target, FAMILIES[target])

    def test_stage1_bundle_is_fully_checksummed(self):
        report = self.registry.readiness('stage1_lr/v1')
        self.assertTrue(report.ready)
        self.assertEqual(len(self.manifest.required_files), 19)

    def test_all_three_approaches_are_available(self):
        for approach, adapter in self.verifiers.items():
            self.assertEqual(adapter.approach, approach)
            self.assertIn('stage1_lr/v1', adapter.name)

    def test_result_contract_and_family_gate(self):
        for approach, verifier in self.verifiers.items():
            for target in TARGETS:
                result = verifier.verify(self.request(target, TEXTS[0]))
                self.assertIn(result.verdict, {'verified','mismatch'})
                self.assertEqual(result.approach, approach)
                self.assertIn(result.predicted_family_id, ('gemini', 'llama'))
                self.assertEqual(result.family_match, result.predicted_family_id == FAMILIES[target])
                self.assertIn('binary_target_score', result.scores)
                self.assertIn('target_validation_threshold', result.thresholds)
                if result.family_match is False:
                    self.assertIsNone(result.model_match)
                    self.assertIsNone(result.predicted_model_id)
                if result.verdict == 'verified':
                    self.assertEqual(result.predicted_model_id, target)
                    self.assertTrue(result.family_match)
                    self.assertTrue(result.model_match)

    def test_expected_family_must_match_expected_model(self):
        bad = FingerprintRequest('bad', Observation('Who?', TEXTS[0]), 'llama3.1-8b', 'gemini')
        with self.assertRaisesRegex(ValueError, 'Expected family'):
            self.verifiers['hierarchy_hard_route'].verify(bad)

    def test_unsupported_expected_model_rejected(self):
        bad = FingerprintRequest('bad', Observation('Who?', TEXTS[0]), 'qwen3-8b', 'qwen')
        with self.assertRaisesRegex(ValueError, 'not supported'):
            self.verifiers['hierarchy_hard_route'].verify(bad)

    def test_real_factory_stage1_only_without_stage2_weights(self):
        constructors = AdapterConstructors()
        constructors.register_stage1('logistic_regression', build_logistic_regression)
        factory = PipelineFactory(self.registry, constructors)  # require_ready=True
        cfg = load_pipeline_config(ROOT / 'config/production.yaml', self.registry)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            verifier = factory.build_stage1(cfg)
        self.assertEqual(verifier.approach, 'hierarchy_hard_route')
        self.assertIn(verifier.verify(self.request(TARGETS[0], TEXTS[0])).verdict, ('verified','mismatch'))
        # Full factory must still correctly refuse missing Stage 2 builders.
        with self.assertRaisesRegex(FactoryError, 'Stage 2 builder'):
            factory.build(cfg)

    def test_real_stage1_runs_inside_pipeline_with_stub_stage2(self):
        # The Stage 2 identifier here is deliberately a stub: this tests the
        # real Stage 1 inside the actual production orchestrator.
        from fingerprinting.pipeline import FingerprintPipeline
        from fingerprinting.strategies import SingleMethodStrategy
        from fingerprinting.testing import StubIdentifier
        from fingerprinting.schemas import IdentificationResult
        stage2_stub = StubIdentifier('lora', IdentificationResult('lora', 'unknown'))
        pipeline = FingerprintPipeline(self.verifiers['hierarchy_hard_route'],
                                       SingleMethodStrategy(stage2_stub))
        verified_req = self.request('gemini-3.8-flash', TEXTS[0])
        verified_result = pipeline.run(verified_req)
        self.assertEqual(verified_result.final.status, 'verified')
        self.assertEqual(verified_result.final.resolved_by, 'stage1')
        self.assertEqual(len(stage2_stub.calls), 0)
        changed_req = self.request('gemini-3.1-pro', TEXTS[0])
        unresolved_result = pipeline.run(changed_req)
        self.assertEqual(unresolved_result.stage1.verdict, 'mismatch')
        self.assertEqual(unresolved_result.final.status, 'needs_review')
        self.assertEqual([r.method for r in unresolved_result.stage2_attempts], ['lora'])
        self.assertEqual(len(stage2_stub.calls), 1)

    def test_target_scores_match_original_inference_script(self):
        # Original code MUST match numeric scores and threshold decisions, even
        # though the new *verdict* has an additional model-identity requirement.
        src = ROOT / 'reference_stage1/scripts'
        sys.path.insert(0, str(src))
        try:
            orig = importlib.import_module('predict_hierarchical')
            with tempfile.TemporaryDirectory() as td:
                base = Path(td)
                shutil.copytree(self.manifest.directory, base / 'models/baseline_lr')
                # Avoid re-deserializing the same 7 models for every target.
                import joblib
                loader = joblib.load
                cached_load = lru_cache(maxsize=None)(lambda p: loader(p))
                with patch.object(orig.joblib, 'load', side_effect=cached_load), warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    for approach in self.verifiers:
                        for target in TARGETS:
                            for response in TEXTS[:2]:
                                original = orig.predict(response, base, 'baseline_lr', target, approach)
                                current = self.verifiers[approach].verify(self.request(target,response))
                                self.assertAlmostEqual(current.scores['binary_target_score'],
                                                       original['binary_target_score'], places=10)
                                self.assertAlmostEqual(current.scores['family_score_gemini'],
                                                       original['family_score_gemini'], places=10)
                                self.assertEqual(bool(current.scores['original_predicted_target']),
                                                 original['predicted_target'])
                                self.assertAlmostEqual(current.thresholds['target_validation_threshold'],
                                                       original['validation_threshold'],places=15)
                                self.assertEqual(current.predicted_family_id,
                                                 original['family_routed_to'])
        finally:
            sys.path.remove(str(src))


if __name__ == '__main__':
    unittest.main()
