"""Stage 2C tests: real refitted model + original preprocessing + strategy routing."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from fingerprinting.adapters.random_forest import (RandomForestIdentifier,
    RFConfigurationError, build_random_forest)
from fingerprinting.config import load_pipeline_config
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import (EvaluationCase, FingerprintRequest,
    IdentificationInput, IdentificationResult, Observation, Stage1Result)
from fingerprinting.strategies import FallbackStrategy
from fingerprinting.testing import StubIdentifier, StubStage1
from fingerprinting.pipeline import FingerprintPipeline

ROOT = (Path(__file__).resolve().parents[2] / 'system')
LABELS = ['gemma3-4b','llama3.1-8b','llama3.2-3b','qwen3-8b','qwen3.5-9b']
RAW = ROOT.parent/'tests/fixtures/random_forest/heldout_raw_cases.jsonl'
FEATURES = ROOT.parent/'tests/fixtures/random_forest/rf_P13_test.csv'


def records():
    return [json.loads(s) for s in RAW.read_text(encoding='utf-8').splitlines() if s]


def observation(row):
    return Observation(row['prompt'], row['response_text'], row['prompt_id'],
                       int(float(row['output_tokens'])) if row['output_tokens'] else None,
                       float(row['latency_ms']) if row['latency_ms'] else None)


class RandomForestAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')
        cls.registry = ArtifactRegistry(ROOT, cls.catalog)
        cls.manifest = cls.registry.get('random_forest/v1')
        cls.rows = records()

    def test_manifest_readiness(self):
        self.assertTrue(self.registry.readiness('random_forest/v1').ready)
        self.assertEqual(self.manifest.options['label_order'], LABELS)

    def test_factory_build_only_random_forest(self):
        cfg = load_pipeline_config(ROOT/'config/experiments/random_forest_only.yaml', self.registry)
        constructors = AdapterConstructors()
        constructors.register_stage2('random_forest', build_random_forest)
        stage2 = PipelineFactory(self.registry, constructors).build_stage2(cfg)
        self.assertEqual([i.name for i in stage2.identifiers], ['random_forest'])
        result = stage2.execute(IdentificationInput(initial=observation(self.rows[0])))
        self.assertEqual(result.attempts[0].method, 'random_forest')
        self.assertIn(result.attempts[0].candidate_model_id, LABELS)
        self.assertIsNone(result.accepted_model_id)
        self.assertEqual(result.attempts[0].outcome, 'unknown')
        self.assertTrue(result.attempts[0].handoff_requested)

    def test_feature_reconstruction_matches_original_heldout_tables(self):
        method = RandomForestIdentifier(self.manifest, predictor=lambda x: dict(zip(LABELS,[1,0,0,0,0])))
        actual = pd.concat([method.make_feature_frame(observation(r)) for r in self.rows], ignore_index=True)
        expected = pd.read_csv(FEATURES).drop(columns='model_key')
        self.assertEqual(list(actual.columns), list(expected.columns))
        self.assertEqual(len(actual), len(expected))
        np.testing.assert_allclose(actual.to_numpy(dtype=float), expected.to_numpy(dtype=float),
                                   rtol=1e-9, atol=1e-7, equal_nan=True)

    def test_training_labels_are_not_in_inference_inputs(self):
        method = RandomForestIdentifier(self.manifest, predictor=lambda x: dict(zip(LABELS,[1,0,0,0,0])))
        cols = method.make_feature_frame(observation(self.rows[0])).columns
        self.assertNotIn('model_key', cols)
        self.assertNotIn('expected_model', cols)

    def test_all132_reproduces_exported_classifier_predictions(self):
        method = RandomForestIdentifier(self.manifest)
        expected = pd.read_csv(FEATURES)['model_key']
        preds = [method.identify(IdentificationInput(initial=observation(r))).candidate_model_id
                 for r in self.rows]
        self.assertEqual(int(sum(x==y for x,y in zip(preds, expected))), 123)
        # Exact parity with the rebuilt model on exported numeric features.
        import joblib
        model = joblib.load(ROOT/'models/random_forest/v1/classifier.joblib')
        predicted_from_features = model.predict(pd.read_csv(FEATURES).drop(columns='model_key'))
        self.assertEqual(preds, predicted_from_features.tolist())

    def test_review_only_does_not_claim_drift(self):
        method = RandomForestIdentifier(self.manifest)
        result = method.identify(IdentificationInput(initial=observation(self.rows[0])))
        self.assertEqual(result.outcome, 'unknown')
        self.assertIsNone(result.accepted_model_id)
        self.assertAlmostEqual(sum(result.model_scores.values()), 1, places=4)
        self.assertEqual(result.score_type, 'rf_predict_proba')

    def test_unknown_prompt_and_missing_backend_are_reported(self):
        method = RandomForestIdentifier(self.manifest, predictor=lambda x: dict(zip(LABELS,[1,0,0,0,0])))
        obs = Observation('New task', 'This is a response', 'unseen-prompt')
        result = method.identify(IdentificationInput(initial=obs))
        self.assertFalse(result.diagnostics['prompt_id_known'])
        self.assertTrue(result.diagnostics['output_tokens_missing'])
        self.assertTrue(result.diagnostics['latency_ms_missing'])
        self.assertTrue(result.diagnostics['distribution_shift_warning'])

    def test_rejects_bad_predictions(self):
        obs = observation(self.rows[0])
        with self.assertRaisesRegex(ValueError, 'scores do not match'):
            RandomForestIdentifier(self.manifest, predictor=lambda x: {'wrong':1.}).identify(IdentificationInput(initial=obs))
        with self.assertRaisesRegex(ValueError, 'normalized'):
            RandomForestIdentifier(self.manifest, predictor=lambda x: dict(zip(LABELS,[2,0,0,0,0]))).identify(IdentificationInput(initial=obs))

    def test_threshold_policy_must_be_validated(self):
        bad = dict(self.manifest.options)
        bad['acceptance_policy'] = {'mode':'validated_threshold','threshold':0.8}
        with self.assertRaisesRegex(RFConfigurationError, 'unknown-model validation'):
            RandomForestIdentifier(replace(self.manifest, options=bad), predictor=lambda x: dict(zip(LABELS,[1,0,0,0,0])))

    def test_optional_validated_policy_accepts_fixture_only(self):
        opts = dict(self.manifest.options)
        opts['acceptance_policy'] = {'mode':'validated_threshold','threshold':0.8,
                                    'validation_id':'test-fixture-only','includes_unknown_models':True}
        method = RandomForestIdentifier(replace(self.manifest, options=opts),
                     predictor=lambda x: dict(zip(LABELS,[0.9,0.025,0.025,0.025,0.025])))
        r=method.identify(IdentificationInput(initial=observation(self.rows[0])))
        self.assertEqual(r.accepted_model_id,'gemma3-4b')
        self.assertEqual(r.outcome,'identified')
        # Not a production policy: this only tests the interface.

    def test_fallback_last_method_returns_candidate_without_acceptance(self):
        method = RandomForestIdentifier(self.manifest)
        stub = StubIdentifier('lora', IdentificationResult('lora','unknown'))
        fallback = FallbackStrategy([stub, method])
        r = fallback.execute(IdentificationInput(initial=observation(self.rows[0])))
        self.assertEqual([a.method for a in r.attempts], ['lora','random_forest'])
        self.assertIsNone(r.accepted_model_id)
        self.assertIsNotNone(r.attempts[1].candidate_model_id)

    def test_stage2_independent_evaluation_measures_candidate_accuracy(self):
        method = RandomForestIdentifier(self.manifest)
        cases=[]
        for i,row in enumerate(self.rows[:10]):
            o=observation(row)
            cases.append(EvaluationCase(f'rf-{i}', FingerprintRequest(f'rf-{i}',o,'llama3.1-8b','llama'),
                        row['model_key'], self.catalog.get(row['model_key']).family_id,
                        self.manifest.provenance['training_dataset_id'], 'response-held-out'))
        report=EvaluationRunner.stage2(cases, FallbackStrategy([method]))
        stat=report.metrics['by_method']['random_forest']
        self.assertEqual(stat['candidate_predictions'], 10)
        self.assertEqual(stat['accepted'], 0)
        self.assertIsNotNone(stat['candidate_top1_accuracy'])


if __name__ == '__main__':
    unittest.main()

class RandomForestIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ROOT
        cls.catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')
        cls.registry = ArtifactRegistry(ROOT, cls.catalog)
        cls.rows = records()

    def test_real_stage1_then_real_random_forest_through_factory(self):
        from fingerprinting.adapters.logistic_regression import build_logistic_regression
        cfg=load_pipeline_config(ROOT/'config/experiments/random_forest_only.yaml',self.registry)
        builders=AdapterConstructors()
        builders.register_stage1('logistic_regression',build_logistic_regression)
        builders.register_stage2('random_forest',build_random_forest)
        pipeline=PipelineFactory(self.registry,builders).build(cfg)
        # Gemma is outside Stage 1's two trained families. It should fall
        # through to the forest here; Stage 1 can make false matches on other
        # unseen models, which this smoke test does not rule out.
        r=next(r for r in self.rows if r['model_key']=='gemma3-4b')
        output=pipeline.run(FingerprintRequest('real-stage1-rf',observation(r),'llama3.1-8b','llama'), use_stage1=True)
        self.assertEqual(output.stage1.verdict,'mismatch')
        self.assertEqual([a.method for a in output.stage2_attempts], ['random_forest'])
        self.assertEqual(output.final.status,'needs_review')
        self.assertEqual(output.stage2_attempts[0].candidate_model_id, 'gemma3-4b')
        self.assertEqual(output.artifact_ids['random_forest'],'random_forest/v1')

    def test_fallback_three_methods_reaches_forest_without_claiming_identity(self):
        stage1=StubStage1('always-mismatch',Stage1Result('mismatch',family_match=False))
        lora=StubIdentifier('lora',IdentificationResult('lora','unknown'))
        harness=StubIdentifier('harness',IdentificationResult('harness','unknown'))
        forest=RandomForestIdentifier(self.registry.get('random_forest/v1'))
        pipeline=FingerprintPipeline(stage1,FallbackStrategy([lora,harness,forest]))
        result=pipeline.run(FingerprintRequest('three-methods',observation(self.rows[0]),'llama3.1-8b','llama'))
        self.assertEqual([a.method for a in result.stage2_attempts], ['lora','harness','random_forest'])
        self.assertEqual(result.final.status,'needs_review')
        self.assertIsNotNone(result.stage2_attempts[-1].candidate_model_id)
