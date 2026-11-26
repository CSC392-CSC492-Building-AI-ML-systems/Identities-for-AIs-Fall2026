"""Unified evaluation logic: deterministic synthetic strategies, no external API calls."""
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace

from fingerprinting.eval_cases import (EvaluationDataError, case_to_dict, dataset_profile,
                                       parse_case, read_cases, write_cases, convert_rf_holdout)
from fingerprinting.eval_suite import (with_stage2, with_stage1_approach, confidence_interval,
                                       run_suite, save_suite)
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import EvaluationCase, FingerprintRequest, Observation, Stage1Result, IdentificationResult
from fingerprinting.testing import StubStage1, StubIdentifier

ROOT = (Path(__file__).resolve().parents[2] / 'system')


class UnifiedEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')
        cls.registry = ArtifactRegistry(ROOT, cls.catalog)
        cls.config = load_pipeline_config(ROOT/'config/production.yaml', cls.registry)

    def case(self, expected='llama3.1-8b', actual='llama3.2-3b', case_id='a'):
        request = FingerprintRequest(case_id, Observation('Prompt X', 'Response Y', 'P-001'),
                                     expected, self.catalog.get(expected).family_id)
        return EvaluationCase(case_id, request, actual, self.catalog.get(actual).family_id,
                              'fixture', 'test', source_record_ids=['raw-source-1'])

    @staticmethod
    def constructors():
        builders = AdapterConstructors()
        def s1(manifest, config):
            return StubStage1('test_stage1', Stage1Result('mismatch', family_match=True, model_match=False))
        def s2(manifest, selection):
            accepted = selection.adapter == 'harness'
            return StubIdentifier(selection.adapter, IdentificationResult(
                selection.adapter, 'identified' if accepted else 'unknown',
                candidate_model_id='llama3.2-3b',
                accepted_model_id='llama3.2-3b' if accepted else None))
        builders.register_stage1('logistic_regression', s1)
        for n in ('lora','harness','random_forest'):
            builders.register_stage2(n, s2)
        return builders

    def test_parse_roundtrip(self):
        case = self.case()
        restored = parse_case(case_to_dict(case), self.catalog)
        self.assertEqual(case, restored)

    def test_reject_conflicting_family(self):
        raw = case_to_dict(self.case())
        raw['expected_family_id'] = 'gemini'
        with self.assertRaises(EvaluationDataError):
            parse_case(raw, self.catalog)

    def test_reject_unknown_model_without_family(self):
        raw = case_to_dict(self.case())
        raw['actual_model_id'] = 'unregistered-unknown'
        raw['actual_family_id'] = None
        with self.assertRaises(EvaluationDataError):
            parse_case(raw, self.catalog)

    def test_accept_out_of_catalog_actual_with_explicit_family(self):
        raw = case_to_dict(self.case())
        raw['actual_model_id'] = 'brand-new-unknown-model'
        raw['actual_family_id'] = 'new-family'
        case = parse_case(raw, self.catalog)
        self.assertEqual(case.actual_model_id, 'brand-new-unknown-model')
        self.assertEqual(case.request.expected_model_id, 'llama3.1-8b')

    def test_reject_wrong_probe_id(self):
        raw = case_to_dict(self.case())
        raw['replay_probes'] = {'I1': {'prompt_id':'I2', 'prompt_text':'q','response_text':'r'}}
        with self.assertRaises(EvaluationDataError):
            parse_case(raw, self.catalog)

    def test_read_write_and_duplicate_case(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cases.jsonl'
            write_cases([self.case()], path)
            self.assertEqual(read_cases(path, self.catalog), [self.case()])
            path.write_text(path.read_text()*2)
            with self.assertRaises(EvaluationDataError):
                read_cases(path, self.catalog)

    def test_profile_repeated_sources_count_once(self):
        cases=[self.case(case_id='a'), self.case(case_id='b')]
        self.assertEqual(dataset_profile(cases)['unique_source_observations'], 1)

    def test_invalid_stage2_override(self):
        with self.assertRaises(ValueError):
            with_stage2(self.config, self.config.stage2.methods, 'single')
        with self.assertRaises(ValueError):
            with_stage2(self.config, [], 'fallback')

    def test_hash_updates_with_method_or_stage1(self):
        cfg = with_stage2(self.config, [self.config.stage2.methods[1]], 'single')
        self.assertNotEqual(cfg.config_sha256, self.config.config_sha256)
        cfg2 = with_stage1_approach(self.config, 'hierarchy_soft')
        self.assertNotEqual(cfg2.config_sha256, self.config.config_sha256)

    def test_suite_independent_and_e2e_mock(self):
        cases=[self.case()]
        factory=PipelineFactory(self.registry, self.constructors(), require_ready=False)
        report=run_suite(cases, self.config, self.registry, factory, scope='all',judge_provider='google')
        self.assertEqual(len(report['reports']), 5) # stage1, 3 methods, e2e
        self.assertEqual(report['reports']['e2e']['metrics']['drift_detected'], 1)
        self.assertEqual(report['reports']['e2e']['rows'][0]['resolved_by'], 'harness')
        self.assertEqual(report['reports']['stage2/lora']['metrics']['by_method']['lora']['candidate_top1_accuracy'], 1.)

    def test_mock_judge_suppresses_accuracy_claim(self):
        factory=PipelineFactory(self.registry, self.constructors(), require_ready=False)
        report=run_suite([self.case()], self.config, self.registry, factory, scope='stage2', methods=['harness'])
        harness=report['reports']['stage2/harness']
        self.assertEqual(harness['status'], 'completed_diagnostic_only')
        self.assertIsNone(harness['metrics']['exact_accuracy_all_cases'])

    def test_real_readiness_blocks_historical_v1_but_not_installed_v2(self):
        from fingerprinting.config import Stage2MethodSelection
        factory=PipelineFactory(self.registry, self.constructors(), require_ready=True)
        old_config=with_stage2(self.config,
            [Stage2MethodSelection('lora','lora/v1'),*self.config.stage2.methods[1:]],'fallback')
        report=run_suite([self.case()], old_config, self.registry, factory, scope='e2e')
        self.assertIn('e2e', report['blocked'])
        self.assertIn('lora/v1', report['blocked']['e2e'])
        current=run_suite([self.case()],self.config,self.registry,factory,scope='e2e')
        self.assertIn('e2e',current['reports'])

    def test_partial_e2e_opt_in_with_missing_historical_v1(self):
        from fingerprinting.config import Stage2MethodSelection
        factory=PipelineFactory(self.registry, self.constructors(), require_ready=True)
        old_config=with_stage2(self.config,
            [Stage2MethodSelection('lora','lora/v1'),*self.config.stage2.methods[1:]],'fallback')
        report=run_suite([self.case()], old_config, self.registry, factory,
                         scope='e2e',allow_partial_e2e=True)
        self.assertIn('e2e', report['reports'])
        self.assertTrue(report['reports']['e2e']['partial_pipeline'])
        self.assertEqual(report['reports']['e2e']['omitted_methods'], ['lora'])

    def test_choose_only_rf_marks_e2e_as_subset(self):
        factory=PipelineFactory(self.registry, self.constructors(), require_ready=True)
        report=run_suite([self.case()], self.config, self.registry, factory, scope='e2e', methods=['random_forest'])
        self.assertTrue(report['reports']['e2e']['partial_pipeline'])
        self.assertEqual(report['reports']['e2e']['omitted_methods'], ['lora','harness'])

    def test_save_report_does_not_copy_prompt_response(self):
        factory=PipelineFactory(self.registry, self.constructors(), require_ready=False)
        report=run_suite([self.case()], self.config, self.registry, factory, scope='all')
        with tempfile.TemporaryDirectory() as directory:
            save_suite(report, directory, dataset_source='synthetic',dataset_sha256='0'*64)
            self.assertTrue((Path(directory)/'summary.md').is_file())
            self.assertTrue((Path(directory)/'metrics.csv').is_file())
            self.assertNotIn('Response Y', (Path(directory)/'case_results.csv').read_text())
            self.assertEqual(len(json.loads((Path(directory)/'summary.json').read_text())['report_files']),5)

    def test_wilson_interval(self):
        self.assertIsNone(confidence_interval(0,0))
        a = confidence_interval(5,10)
        self.assertLess(a['low'], 0.5)
        self.assertGreater(a['high'], 0.5)

    def test_rf_pilot_conversion_labels_and_source_reuse(self):
        cases=convert_rf_holdout(ROOT.parent/'tests/fixtures/random_forest/heldout_raw_cases.jsonl', self.catalog, limit_per_model=1)
        self.assertGreaterEqual(len(cases),5)
        self.assertTrue(any(x.actual_model_id!=x.request.expected_model_id for x in cases))
        self.assertTrue(all(x.request.expected_model_id in {'llama3.1-8b','llama3.2-3b','gemini-3.1-pro','gemini-3.8-flash'} for x in cases))
        self.assertLess(dataset_profile(cases)['unique_source_observations'], len(cases))

    def test_harness_paired_replay_fixture_has_six_probes(self):
        cases=read_cases(ROOT.parent/'tests/fixtures/evaluation/harness_bk1_replay_cases.jsonl', self.catalog)
        self.assertEqual(len(cases),2)
        self.assertEqual(dataset_profile(cases)['cases_with_complete_harness_probe_set'],2)


if __name__ == '__main__':
    unittest.main()
