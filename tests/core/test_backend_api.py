"""Offline HTTP tests: no external provider requests or classifier accuracy claims."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# `system/run.py test` executes from system/, while HTTP imports use system.*.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from system.backend.app import create_app
from system.backend.services.analysis import make_mock_gateway
from system.fingerprinting.clients import CallableTargetClient
from system.fingerprinting.pipeline import FingerprintPipeline
from system.fingerprinting.schemas import IdentificationResult
from system.fingerprinting.strategies import SingleMethodStrategy
from system.fingerprinting.testing import StubIdentifier
from system.fingerprinting.workflow import PromptAnalysisService


class HttpApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gateway = make_mock_gateway()
        cls.client = TestClient(create_app(cls.gateway))

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_health(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'status': 'ok', 'mode': 'mock'})

    def test_capabilities_disclose_prototype_limitations(self):
        r = self.client.get('/api/v1/capabilities')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d['mode'], 'mock')
        self.assertTrue(d['prompt_only'])
        self.assertFalse(d['stage1_enabled_by_default'])
        self.assertFalse(d['stage1_available'])
        self.assertFalse(d['accepts_api_keys'])
        self.assertFalse(d['live_provider_available'])
        self.assertFalse(d['live_judge_available'])
        self.assertFalse(d['accepted_model_identification_available'])
        self.assertFalse(d['verified_model_cards'])

    def test_openapi_includes_analysis_route(self):
        d = self.client.get('/openapi.json').json()
        self.assertIn('/api/v1/analyze', d['paths'])
        self.assertIn('post', d['paths']['/api/v1/analyze'])

    def test_prompt_to_seven_queries_including_real_harness_probes(self):
        r = self.client.post('/api/v1/analyze', json={'prompt_text': 'Explain recursion.'})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d['mode'], 'mock')
        self.assertEqual(d['status'], 'needs_review')
        self.assertIsNone(d['model_id'])
        self.assertFalse(d['stage1_enabled'])
        self.assertEqual(d['target_queries'],
                         ['UI-INITIAL', 'LM-01', 'LM-05', 'LM-06', 'I1', 'I2', 'V1-15'])
        self.assertEqual(d['model_card_status'], 'unconfirmed')
        self.assertEqual(d['change_status'], 'no_baseline')
        self.assertEqual(d['report']['fingerprint']['stage1']['verdict'], 'skipped')
        self.assertEqual(d['report']['fingerprint']['stage2_attempts'][0]['method'], 'harness')
        self.assertEqual(d['report']['fingerprint']['stage2_attempts'][0]['outcome'], 'unknown')
        self.assertEqual(d['report']['card_changes'], [])
        self.assertNotIn('Explain recursion.', json.dumps(d))

    def test_identifiers_unique_between_requests(self):
        a = self.client.post('/api/v1/analyze', json={'prompt_text':'A'}).json()
        b = self.client.post('/api/v1/analyze', json={'prompt_text':'B'}).json()
        self.assertNotEqual(a['request_id'], b['request_id'])

    def test_missing_prompt_is_rejected(self):
        self.assertEqual(self.client.post('/api/v1/analyze', json={}).status_code, 422)

    def test_whitespace_prompt_is_rejected(self):
        self.assertEqual(self.client.post('/api/v1/analyze', json={'prompt_text':'  \n '}).status_code, 422)

    def test_non_string_prompt_is_rejected(self):
        self.assertEqual(self.client.post('/api/v1/analyze', json={'prompt_text':123}).status_code, 422)

    def test_long_prompt_is_rejected(self):
        self.assertEqual(self.client.post('/api/v1/analyze', json={'prompt_text':'a'*8001}).status_code, 422)

    def test_api_key_field_is_rejected_not_echoed(self):
        r = self.client.post('/api/v1/analyze', json={
            'prompt_text':'Hello', 'api_key':'NEVER_RECORD_THIS_KEY'})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn('NEVER_RECORD_THIS_KEY', r.text)

    def test_manual_response_and_probe_fields_rejected(self):
        for extra in ['response_text', 'probes']:
            r = self.client.post('/api/v1/analyze', json={'prompt_text':'Hi', extra:'manual'})
            self.assertEqual(r.status_code, 422)

    def test_stage1_opt_in_requires_confirmed_baseline(self):
        r = self.client.post('/api/v1/analyze', json={'prompt_text':'Hello', 'use_stage1':True})
        self.assertEqual(r.status_code, 409)
        self.assertIn('confirmed baseline', r.json()['detail'])

    def test_stage1_type_validation(self):
        r = self.client.post('/api/v1/analyze', json={'prompt_text':'Hi', 'use_stage1':'yes'})
        self.assertEqual(r.status_code, 422)

    def test_internal_exception_does_not_expose_sensitive_details(self):
        class ExplodingGateway:
            def analyze(self, prompt_text, *, use_stage1=False):
                raise RuntimeError('user-api-key-SECRET-EXAMPLE')
        with TestClient(create_app(ExplodingGateway())) as client:
            r = client.post('/api/v1/analyze', json={'prompt_text':'Hi'})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json(), {'detail':'Analysis failed'})
        self.assertNotIn('SECRET-EXAMPLE', r.text)

    def test_backend_preserves_accepted_vs_unaccepted_semantics(self):
        # Inject a synthetic accepted result to test schema; NEVER real accuracy.
        gateway = make_mock_gateway()
        synthetic = StubIdentifier('random_forest', IdentificationResult(
            method='random_forest', outcome='identified', accepted_model_id='llama3.1-8b'))
        gateway.workflow = PromptAnalysisService(
            FingerprintPipeline(None, SingleMethodStrategy(synthetic), stage1_enabled=False),
            gateway.workflow.catalog)
        with TestClient(create_app(gateway)) as client:
            d = client.post('/api/v1/analyze', json={'prompt_text':'Hello'}).json()
        self.assertEqual(d['mode'], 'mock')
        self.assertEqual(d['status'], 'identified')
        self.assertEqual(d['model_id'], 'llama3.1-8b')
        self.assertEqual(d['change_status'], 'no_baseline')
        self.assertEqual(d['model_card_status'], 'unavailable')
        self.assertEqual(d['target_queries'], ['UI-INITIAL'])


if __name__ == '__main__':
    unittest.main()
