"""Authenticated encrypted live-job tests. All target calls are fakes; no cost."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from system.backend.app import create_app
from system.backend.jobs.live_store import SqliteLiveJobStore
from system.backend.jobs.live_runner import LiveJobWorker
from system.backend.providers.openai import ProviderRequestError
from system.backend.security.auth import LocalTokenAuth
from system.backend.security.crypto import FileSecretVault, LiveCrypto
from system.backend.services.analysis import make_mock_gateway
from system.backend.services.live import LiveOpenAIAnalysisGateway

TOKEN_A = 'A' * 45 + '-owner'
TOKEN_B = 'B' * 45 + '-owner'
SENTINEL = 'TEST_REAL_PROVIDER_KEY_DO_NOT_LEAK_238894'
PROMPT = 'UNIQUE_PRIVATE_PROMPT_238894'


class FakeProvider:
    all_calls = []

    def __init__(self, key: str, model: str):
        self.key = key
        self.model = model
        self.prompts = []
        self.closed = False
        self.all_calls.append(self)

    def send_prompt(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return 'Offline fake response from a controlled target.'

    def close(self):
        self.closed = True


class LiveJobTests(unittest.TestCase):
    def setUp(self):
        FakeProvider.all_calls.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / 'jobs.sqlite3'
        self.crypto = LiveCrypto(Fernet.generate_key())
        self.store = SqliteLiveJobStore(self.crypto, self.db_path)
        self.vault = FileSecretVault(self.crypto, Path(self.temp.name) / 'vault')
        self.auth = LocalTokenAuth({'alice': hashlib.sha256(TOKEN_A.encode()).hexdigest(),
                                    'bob': hashlib.sha256(TOKEN_B.encode()).hexdigest()})
        self.mock = make_mock_gateway()
        self.live = LiveOpenAIAnalysisGateway(self.mock.workflow, provider_factory=FakeProvider)
        self.client = TestClient(create_app(self.mock, self.live,
                                            token_auth=self.auth, live_job_store=self.store,
                                            secret_vault=self.vault))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def headers(self, token=TOKEN_A):
        return {'Authorization': f'Bearer {token}'}

    def payload(self, **overrides):
        return {'prompt_text': PROMPT, 'provider': 'openai',
                'target_model': 'gpt-test-id', 'api_key': SENTINEL,
                'use_stage1': False, **overrides}

    def enqueue(self, token=TOKEN_A, **overrides):
        return self.client.post('/api/v1/fingerprint/live-jobs', json=self.payload(**overrides),
                                headers=self.headers(token))

    def worker(self):
        return LiveJobWorker(SqliteLiveJobStore(self.crypto, self.db_path), self.vault, self.live)

    def test_live_job_auth_required_and_safe_errors(self):
        for headers in ({}, {'Authorization': 'Bearer wrong'}, {'Authorization': 'Basic invalid'}):
            with self.subTest(headers=headers):
                response = self.client.post('/api/v1/fingerprint/live-jobs',
                                            json=self.payload(), headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn(SENTINEL, response.text)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM fingerprint_live_jobs').fetchone()[0], 0)

    def test_full_lifecycle_and_seven_provider_queries(self):
        response = self.enqueue()
        self.assertEqual(response.status_code, 202, response.text)
        job_id = response.json()['job_id']
        self.assertEqual(response.headers['Location'], f'/api/v1/fingerprint/live-jobs/{job_id}')
        initial = self.client.get(response.headers['Location'], headers=self.headers()).json()
        self.assertEqual(initial['status'], 'queued')
        self.assertIsNone(initial['result'])
        self.assertEqual(self.worker().run_once(), job_id)
        self.assertIsNone(self.worker().run_once())
        after = self.client.get(response.headers['Location'], headers=self.headers())
        self.assertEqual(after.status_code, 200)
        result = after.json()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['mode'], 'live_target_mock_judge')
        self.assertEqual(result['result']['status'], 'needs_review')
        self.assertEqual(result['result']['target_queries'],
                         ['UI-INITIAL','LM-01','LM-05','LM-06','I1','I2','V1-15'])
        self.assertEqual(len(FakeProvider.all_calls), 1)
        self.assertEqual(len(FakeProvider.all_calls[0].prompts), 7)
        self.assertEqual(FakeProvider.all_calls[0].key, SENTINEL)
        self.assertEqual(FakeProvider.all_calls[0].model, 'gpt-test-id')
        self.assertTrue(FakeProvider.all_calls[0].closed)
        self.assertFalse(self.vault._file(job_id).exists())
        for secret in (SENTINEL, PROMPT, TOKEN_A, TOKEN_B):
            self.assertNotIn(secret, after.text)

    def test_db_and_vault_never_contain_plaintext_sensitive_data(self):
        job_id = self.enqueue().json()['job_id']
        db = self.db_path.read_bytes()
        vault_bytes = self.vault._file(job_id).read_bytes()
        for secret in (SENTINEL, PROMPT, TOKEN_A, TOKEN_B):
            self.assertNotIn(secret.encode(), db)
            self.assertNotIn(secret.encode(), vault_bytes)
        with closing(sqlite3.connect(self.db_path)) as conn:
            req = conn.execute('SELECT request_ciphertext,result_ciphertext FROM fingerprint_live_jobs WHERE job_id=?',
                               (job_id,)).fetchone()
        self.assertEqual(self.crypto.open(req[0])['prompt_text'], PROMPT)
        self.assertIsNone(req[1])
        self.worker().run_once()
        with closing(sqlite3.connect(self.db_path)) as conn:
            req = conn.execute('SELECT request_ciphertext,result_ciphertext FROM fingerprint_live_jobs WHERE job_id=?',
                               (job_id,)).fetchone()
        self.assertIsNone(req[0])
        self.assertIsNotNone(req[1])
        self.assertNotIn(PROMPT.encode(), self.db_path.read_bytes())

    def test_owner_isolation_and_non_disclosure(self):
        job_id = self.enqueue().json()['job_id']
        endpoint = f'/api/v1/fingerprint/live-jobs/{job_id}'
        self.assertEqual(self.client.get(endpoint, headers=self.headers(TOKEN_B)).status_code, 404)
        self.worker().run_once()
        self.assertEqual(self.client.get(endpoint, headers=self.headers(TOKEN_B)).status_code, 404)
        self.assertEqual(self.client.get(endpoint, headers=self.headers(TOKEN_A)).status_code, 200)
        self.assertEqual(self.client.get(endpoint).status_code, 401)
        # Legacy unauthenticated mock endpoint must not surface this live job.
        self.assertEqual(self.client.get(f'/api/v1/fingerprint/jobs/{job_id}').status_code, 404)

    def test_stage1_and_wrong_fields_blocked(self):
        response=self.enqueue(use_stage1=True)
        self.assertEqual(response.status_code, 409)
        for extra in ('response_text','probes','other_key'):
            with self.subTest(extra=extra):
                r=self.enqueue(**{extra:SENTINEL})
                self.assertEqual(r.status_code,422)
                self.assertNotIn(SENTINEL,r.text)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM fingerprint_live_jobs').fetchone()[0],0)

    def test_missing_auth_or_crypto_disables_live_service(self):
        with TestClient(create_app(self.mock, self.live, job_store=self.store)) as client:
            r=client.post('/api/v1/fingerprint/live-jobs', json=self.payload(),
                          headers=self.headers())
            self.assertEqual(r.status_code,503)
        caps=self.client.get('/api/v1/capabilities').json()
        self.assertTrue(caps['live_jobs_available'])
        self.assertTrue(caps['accepts_api_keys'])
        self.assertTrue(caps['live_jobs_require_bearer_token'])
        self.assertFalse(caps['live_judge_available'])

    def test_legacy_synchronous_live_disabled_by_default(self):
        response=self.client.post('/api/v1/analyze/live',json=self.payload())
        self.assertEqual(response.status_code,404)
        self.assertEqual(len(FakeProvider.all_calls),0)

    def test_provider_error_is_sanitized_and_vault_cleaned(self):
        class FailingProvider(FakeProvider):
            def send_prompt(self,prompt):
                raise ProviderRequestError('provider_failed',status_code=502,message=SENTINEL)
        worker=LiveJobWorker(self.store,self.vault,
                             LiveOpenAIAnalysisGateway(self.mock.workflow,provider_factory=FailingProvider))
        job_id=self.enqueue().json()['job_id']
        self.assertEqual(worker.run_once(),job_id)
        after=self.client.get(f'/api/v1/fingerprint/live-jobs/{job_id}',headers=self.headers()).json()
        self.assertEqual(after['status'],'failed')
        self.assertEqual(after['error_code'],'PROVIDER_ERROR')
        self.assertIsNone(after['result'])
        self.assertFalse(self.vault._file(job_id).exists())
        self.assertNotIn(SENTINEL,json.dumps(after))

    def test_unexpected_error_is_sanitized(self):
        class FailingProvider(FakeProvider):
            def send_prompt(self,prompt):
                raise RuntimeError('Fatal ' + SENTINEL)
        worker=LiveJobWorker(self.store,self.vault,
                             LiveOpenAIAnalysisGateway(self.mock.workflow,provider_factory=FailingProvider))
        job_id=self.enqueue().json()['job_id']
        worker.run_once()
        after=self.client.get(f'/api/v1/fingerprint/live-jobs/{job_id}',headers=self.headers()).json()
        self.assertEqual(after['error_code'],'ANALYSIS_FAILED')
        self.assertNotIn(SENTINEL,json.dumps(after))
        self.assertFalse(self.vault._file(job_id).exists())

    def test_expired_queued_job_does_not_call_provider(self):
        job_id=self.enqueue().json()['job_id']
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE fingerprint_live_jobs SET expires_at='2000-01-01T00:00:00.000+00:00' WHERE job_id=?",(job_id,))
            conn.commit()
        self.assertIsNone(self.worker().run_once())
        after=self.client.get(f'/api/v1/fingerprint/live-jobs/{job_id}',headers=self.headers()).json()
        self.assertEqual(after['status'],'failed')
        self.assertEqual(after['error_code'],'JOB_EXPIRED')
        self.assertFalse(self.vault._file(job_id).exists())
        self.assertEqual(len(FakeProvider.all_calls),0)

    def test_worker_missing_credential_is_not_retried(self):
        job_id=self.enqueue().json()['job_id']
        self.vault.delete(job_id)
        self.worker().run_once()
        status=self.store.get_for_owner(job_id,'alice')
        self.assertEqual(status['status'],'failed')
        self.assertEqual(status['error_code'],'CREDENTIAL_UNAVAILABLE')
        self.assertEqual(status['attempt_count'],1)
        self.assertIsNone(self.worker().run_once())

    def test_concurrent_live_claims_distinct_jobs(self):
        from concurrent.futures import ThreadPoolExecutor
        job_ids={self.enqueue(prompt_text=f'Safe test prompt {i}').json()['job_id'] for i in range(8)}
        def claim(i):
            return SqliteLiveJobStore(self.crypto,self.db_path).claim_next(f'worker-{i}')
        with ThreadPoolExecutor(max_workers=8) as executor:
            claims=list(executor.map(claim,range(8)))
        self.assertEqual({row[0] for row in claims},job_ids)
        self.assertEqual(len(claims),8)

    def test_abandoned_running_job_is_failed_without_retry(self):
        job_id=self.enqueue().json()['job_id']
        self.store.claim_next('worker-died')
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE fingerprint_live_jobs SET started_at='2000-01-01T00:00:00.000+00:00' WHERE job_id=?",(job_id,))
            conn.commit()
        self.assertIsNone(self.worker().run_once())
        after=self.store.get_for_owner(job_id,'alice')
        self.assertEqual(after['status'],'failed')
        self.assertEqual(after['error_code'],'WORKER_INTERRUPTED')
        self.assertFalse(self.vault._file(job_id).exists())
        self.assertEqual(len(FakeProvider.all_calls),0)

    def test_separate_process_live_worker_expiry_without_billable_calls(self):
        import os,subprocess,sys
        job_id=self.enqueue().json()['job_id']
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE fingerprint_live_jobs SET expires_at='2000-01-01T00:00:00.000+00:00' WHERE job_id=?",(job_id,))
            conn.commit()
        env=os.environ.copy()
        # Our tests use a key supplied as Fernet.generate_key() at setup;
        # recover an identical key from this test fixture below.
        from base64 import urlsafe_b64encode
        env['SYSTEM_JOB_FERNET_KEY']=urlsafe_b64encode(
            self.crypto._cipher._signing_key + self.crypto._cipher._encryption_key).decode()
        env['SYSTEM_SECRET_VAULT_DIR']=str(self.vault.folder)
        run=subprocess.run([sys.executable,'-m','system.backend.worker','--kind','live',
                            '--once','--db-path',str(self.db_path)],
                           env=env,cwd=Path(__file__).resolve().parents[2],
                           capture_output=True,text=True,timeout=45)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertFalse(self.vault._file(job_id).exists())
        self.assertEqual(self.store.get_for_owner(job_id,'alice')['error_code'],'JOB_EXPIRED')

    def test_token_owner_digest_only(self):
        self.assertEqual(self.auth.user_for_token(TOKEN_A),'alice')
        self.assertEqual(self.auth.user_for_token(TOKEN_B),'bob')
        self.assertIsNone(self.auth.user_for_token('other'))
        with self.assertRaises(ValueError):
            LocalTokenAuth({'alice':'not_a_sha256'})
        self.assertNotIn(TOKEN_A,repr(self.auth._user_hashes))

    def test_wrong_cipher_key_cannot_read_jobs_or_credentials(self):
        job_id=self.enqueue().json()['job_id']
        wrong=LiveCrypto(Fernet.generate_key())
        with self.assertRaises(ValueError):
            wrong.open(self.vault._file(job_id).read_text())
        with self.assertRaises(ValueError):
            SqliteLiveJobStore(wrong,self.db_path).claim_next('other-worker')


if __name__=='__main__':
    unittest.main()
