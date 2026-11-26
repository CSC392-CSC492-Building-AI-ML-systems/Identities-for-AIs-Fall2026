"""Milestone 2: exclusively offline HTTPX transports and fake providers.

No test sends a real key, connects to the network, or identifies a real LLM.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from fastapi.testclient import TestClient

from system.backend.app import create_app
from system.backend.providers.openai import (
    API_URL, OpenAIResponsesProvider, ProviderRequestError,
)
from system.backend.services.analysis import make_mock_gateway
from system.backend.services.live import LiveOpenAIAnalysisGateway

SENTINEL = 'DONT-RECORD-THIS-USER-API-KEY'


def completed_response(text='target response'):
    return {
        'id': 'resp_fake', 'status': 'completed',
        'output': [
            {'type': 'reasoning', 'summary': []},
            {'type': 'message', 'content': [
                {'type': 'output_text', 'text': text},
            ]},
        ],
    }


class ResponsesProviderTests(unittest.TestCase):
    def test_request_to_fixed_official_https_url_and_headers(self):
        sent = []
        def handler(req):
            sent.append(req)
            return httpx.Response(200, json=completed_response('real-looking fake reply'))
        with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
            provider = OpenAIResponsesProvider(SENTINEL, 'gpt-test-model', client=transport)
            self.assertEqual(provider.send_prompt('My prompt'), 'real-looking fake reply')
            self.assertIn('api_key=<redacted>', repr(provider))
            self.assertNotIn(SENTINEL, repr(provider))
        self.assertEqual(len(sent), 1)
        req = sent[0]
        self.assertEqual(str(req.url), API_URL)
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.headers['Authorization'], f'Bearer {SENTINEL}')
        payload = json.loads(req.content)
        self.assertEqual(payload['model'], 'gpt-test-model')
        self.assertEqual(payload['input'], 'My prompt')
        self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'], 512)
        self.assertNotIn(SENTINEL, str(payload))

    def test_provider_refuses_redirect_instead_of_forwarding_credentials(self):
        seen = []
        def handler(req):
            seen.append(str(req.url))
            return httpx.Response(302, headers={'Location': 'https://example.invalid/steal'})
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as transport:
            provider = OpenAIResponsesProvider(SENTINEL, 'test-model', client=transport)
            with self.assertRaises(ProviderRequestError) as err:
                provider.send_prompt('prompt')
        self.assertEqual(err.exception.code, 'provider_failed')
        self.assertEqual(seen, [API_URL])

    def test_error_classification_is_redacted(self):
        samples = [(401, 'provider_credentials_rejected', 502),
                   (403, 'provider_credentials_rejected', 502),
                   (429, 'provider_rate_limited', 429),
                   (400, 'provider_invalid_request', 502),
                   (404, 'provider_invalid_request', 502),
                   (500, 'provider_failed', 502)]
        for status, code, public_status in samples:
            with self.subTest(status=status):
                def handler(req):
                    return httpx.Response(status, json={
                        'error': {'message': f'private data {SENTINEL}'}
                    })
                with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
                    provider = OpenAIResponsesProvider(SENTINEL, 'test-model', client=transport)
                    with self.assertRaises(ProviderRequestError) as e:
                        provider.send_prompt('question')
                self.assertEqual(e.exception.code, code)
                self.assertEqual(e.exception.status_code, public_status)
                self.assertNotIn(SENTINEL, str(e.exception))

    def test_incomplete_and_empty_outputs_are_not_valid_fingerprints(self):
        for response in [
            {'status':'incomplete','output':[]},
            {'status':'completed','output':[]},
            {'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]},
        ]:
            with self.subTest(response=response):
                with httpx.Client(transport=httpx.MockTransport(
                    lambda req: httpx.Response(200, json=response))) as transport:
                    provider = OpenAIResponsesProvider(SENTINEL, 'test-model', client=transport)
                    with self.assertRaises(ProviderRequestError):
                        provider.send_prompt('question')

    def test_timeout_is_sanitized(self):
        def handler(req):
            raise httpx.ReadTimeout(f'{SENTINEL}: simulated timeout')
        with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
            provider = OpenAIResponsesProvider(SENTINEL, 'test-model', client=transport)
            with self.assertRaises(ProviderRequestError) as err:
                provider.send_prompt('question')
        self.assertEqual(err.exception.code, 'provider_timeout')
        self.assertNotIn(SENTINEL, str(err.exception))


class LiveBackendHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.created = []
        mock = make_mock_gateway()
        def fake_factory(key, model):
            provider = cls.FakeTarget(key, model)
            cls.created.append(provider)
            return provider
        cls.live = LiveOpenAIAnalysisGateway(mock.workflow, provider_factory=fake_factory)
        cls.client = TestClient(create_app(mock, cls.live, enable_legacy_sync_live=True))

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    class FakeTarget:
        def __init__(self, key, model):
            self.key = key
            self.model = model
            self.prompts = []
            self.closed = False
        def send_prompt(self, prompt):
            self.prompts.append(prompt)
            return 'Fake transport response only; no OpenAI API used.'
        def close(self):
            self.closed = True

    def payload(self, **overrides):
        return {'prompt_text': 'Explain recursion!', 'target_model': 'gpt-test-model',
                'provider': 'openai', 'api_key': SENTINEL, **overrides}

    def test_full_seven_queries_with_real_harness_questions_and_mock_judge(self):
        r = self.client.post('/api/v1/analyze/live', json=self.payload())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body['mode'], 'live_target_mock_judge')
        self.assertEqual(body['status'], 'needs_review')
        self.assertIsNone(body['model_id'])
        self.assertFalse(body['stage1_enabled'])
        self.assertEqual(body['target_queries'],
                         ['UI-INITIAL', 'LM-01', 'LM-05', 'LM-06', 'I1', 'I2', 'V1-15'])
        self.assertEqual(len(self.created[-1].prompts), 7)
        self.assertTrue(self.created[-1].closed)
        self.assertEqual(self.created[-1].model, 'gpt-test-model')
        self.assertNotIn(SENTINEL, r.text)
        self.assertNotIn('Explain recursion!', r.text)
        self.assertEqual(body['model_card_status'], 'unconfirmed')
        self.assertEqual(body['change_status'], 'no_baseline')
        self.assertTrue(body['report']['fingerprint']['stage2_attempts'][0]['diagnostics']['mock_judge'])

    def test_no_key_or_provider_persisted_on_gateway(self):
        live = self.client.app.state.live_analysis_gateway
        self.assertNotIn(SENTINEL, repr(vars(live)))
        self.assertNotIn(SENTINEL, repr(vars(self.client.app.state)))

    def test_live_requires_key_and_model_and_rejects_extra(self):
        for removal in ('api_key', 'target_model'):
            payload = self.payload()
            del payload[removal]
            self.assertEqual(self.client.post('/api/v1/analyze/live', json=payload).status_code, 422)
        r = self.client.post('/api/v1/analyze/live', json=self.payload(
            api_key='   ', response_text='NO', another_key=SENTINEL))
        self.assertEqual(r.status_code, 422)
        self.assertNotIn(SENTINEL, r.text)

    def test_stage1_requires_baseline_and_makes_no_provider_request(self):
        before = len(self.created)
        r = self.client.post('/api/v1/analyze/live', json=self.payload(use_stage1=True))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(before, len(self.created))
        self.assertNotIn(SENTINEL, r.text)

    def test_mock_route_still_rejects_key(self):
        r = self.client.post('/api/v1/analyze', json={
            'prompt_text':'Hello','api_key': SENTINEL})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn(SENTINEL, r.text)

    def test_unexpected_error_never_leaks_key(self):
        mock = make_mock_gateway()
        class BadTarget:
            def send_prompt(self, prompt):
                raise ValueError('bad request included ' + SENTINEL)
        live = LiveOpenAIAnalysisGateway(mock.workflow, provider_factory=lambda k,m: BadTarget())
        with TestClient(create_app(mock, live, enable_legacy_sync_live=True)) as client:
            r = client.post('/api/v1/analyze/live', json=self.payload())
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json(), {'detail':'Analysis failed'})
        self.assertNotIn(SENTINEL, r.text)

    def test_provider_error_maps_to_safe_http_response(self):
        mock = make_mock_gateway()
        class DeniedTarget:
            def send_prompt(self, prompt):
                raise ProviderRequestError('provider_credentials_rejected',
                                           status_code=502, message='Credentials rejected by provider')
        live = LiveOpenAIAnalysisGateway(mock.workflow, provider_factory=lambda k,m: DeniedTarget())
        with TestClient(create_app(mock, live, enable_legacy_sync_live=True)) as client:
            r = client.post('/api/v1/analyze/live', json=self.payload())
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()['detail']['code'], 'provider_credentials_rejected')
        self.assertNotIn(SENTINEL, r.text)


if __name__ == '__main__':
    unittest.main()
