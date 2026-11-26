"""M6 deployment/job linking and stable UI projection; all providers synthetic."""
from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from system.backend.app import create_app
from system.backend.history_store import HistoryStore
from system.backend.jobs.live_runner import LiveJobWorker
from system.backend.jobs.live_store import SqliteLiveJobStore
from system.backend.security.auth import LocalTokenAuth
from system.backend.security.crypto import FileSecretVault, LiveCrypto
from system.backend.services.analysis import make_mock_gateway
from system.backend.services.live import LiveOpenAIAnalysisGateway
from system.backend.ui_results import summarize_unvalidated_live_result

A = 'm6-alice-token-' * 8
B = 'm6-bob-token-' * 8
KEY = 'M6_TEST_PROVIDER_SECRET_NEVER_EXPOSE'
PROMPT = 'm6 private prompt sentinel'


class FakeTarget:
    sent = []

    def __init__(self, key, model):
        self.key, self.model = key, model
        self.calls = []
        self.sent.append(self)

    def send_prompt(self, prompt):
        self.calls.append(prompt)
        return 'Synthetic answer produced by a fake provider.'

    def close(self):
        pass


class DeploymentJobTests(unittest.TestCase):
    def setUp(self):
        FakeTarget.sent.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'jobs.sqlite3'
        self.crypto = LiveCrypto(Fernet.generate_key())
        self.store = SqliteLiveJobStore(self.crypto, self.path)
        self.history = HistoryStore(self.path)
        self.vault = FileSecretVault(self.crypto, Path(self.tmp.name) / 'vault')
        auth = LocalTokenAuth({'alice':hashlib.sha256(A.encode()).hexdigest(),
                               'bob':hashlib.sha256(B.encode()).hexdigest()})
        self.mock = make_mock_gateway()
        self.live = LiveOpenAIAnalysisGateway(self.mock.workflow, provider_factory=FakeTarget)
        self.client = TestClient(create_app(self.mock, self.live, token_auth=auth,
                                            live_job_store=self.store, secret_vault=self.vault,
                                            history_store=self.history))

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def headers(self, token=A):
        return {'Authorization': f'Bearer {token}'}

    def create_deployment(self, token=A):
        r = self.client.post('/api/v1/deployments', headers=self.headers(token), json={
            'label': 'Project GPT alias', 'provider': 'openai',
            'requested_model_id': 'gpt-application-alias'})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()['id']

    def baseline(self, deployment, model='llama3.1-8b'):
        r = self.client.post(f'/api/v1/deployments/{deployment}/baselines', headers=self.headers(),
            json={'model_id':model, 'acknowledge_manual_review':True,
                  'review_note':'Independently verified by the project reviewer'})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def submit(self, token=A, **other):
        return self.client.post('/api/v1/fingerprint/live-jobs', headers=self.headers(token),
             json={'prompt_text':PROMPT, 'api_key':KEY, 'provider':'openai',
                   'use_stage1':False, **other})

    def worker(self):
        return LiveJobWorker(SqliteLiveJobStore(self.crypto, self.path), self.vault, self.live)

    def test_linked_job_pins_reviewed_baseline_and_routing(self):
        deployment = self.create_deployment()
        b1 = self.baseline(deployment)
        r = self.submit(deployment_id=deployment)  # target_model derived by backend
        self.assertEqual(r.status_code, 202, r.text)
        job_id = r.json()['job_id']
        self.assertEqual(r.json()['deployment_id'], deployment)
        self.assertEqual(r.json()['baseline_revision'], 1)
        # Baseline revision changes while job is in the queue.
        b2 = self.baseline(deployment, 'llama3.2-3b')
        self.assertEqual(b2['revision'], 2)
        self.worker().run_once()
        data = self.client.get(f'/api/v1/fingerprint/live-jobs/{job_id}',
                               headers=self.headers()).json()
        self.assertEqual(data['status'], 'completed')
        self.assertEqual(data['deployment_id'], deployment)
        self.assertEqual(data['baseline_revision'], 1)
        view = data['result']['ui_result']
        self.assertEqual(view['baseline']['id'], b1['id'])
        self.assertEqual(view['baseline']['model_id'], 'llama3.1-8b')
        self.assertEqual(view['identification']['status'], 'needs_review')
        self.assertIsNone(view['identification']['accepted_model_id'])
        self.assertEqual(view['comparison']['status'], 'insufficient_evidence')
        self.assertIsNone(view['comparison']['identity_change'])
        self.assertEqual(view['model_card']['status'], 'unavailable')
        self.assertFalse(view['evidence']['baseline_auto_updated'])
        self.assertEqual(len(FakeTarget.sent), 1)
        self.assertEqual(FakeTarget.sent[0].model, 'gpt-application-alias')
        self.assertEqual(len(FakeTarget.sent[0].calls), 7)
        self.assertEqual(len(self.history.list_history('alice', deployment)), 2)
        self.assertNotIn(KEY, str(data))
        self.assertNotIn(PROMPT, str(data))
        listed = self.client.get(f'/api/v1/deployments/{deployment}/jobs',
                                 headers=self.headers()).json()['jobs']
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['baseline_revision'], 1)
        self.assertNotIn(KEY, str(listed))

    def test_linked_job_without_baseline_is_no_baseline(self):
        deployment = self.create_deployment()
        r = self.submit(deployment_id=deployment)
        self.assertEqual(r.status_code, 202, r.text)
        self.assertIsNone(r.json()['baseline_revision'])
        self.worker().run_once()
        data = self.client.get(f'/api/v1/fingerprint/live-jobs/{r.json()["job_id"]}',
                               headers=self.headers()).json()
        self.assertEqual(data['result']['ui_result']['comparison']['status'], 'no_baseline')
        self.assertIsNone(data['result']['ui_result']['baseline'])
        self.assertEqual(self.history.list_history('alice', deployment), [])

    def test_other_owner_cannot_link_or_list_jobs(self):
        deployment = self.create_deployment()
        self.baseline(deployment)
        r = self.submit(token=B, deployment_id=deployment)
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(KEY, r.text)
        self.assertEqual(self.client.get(f'/api/v1/deployments/{deployment}/jobs',
                                         headers=self.headers(B)).status_code,404)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM fingerprint_live_jobs').fetchone()[0], 0)
        self.assertFalse(list((Path(self.tmp.name)/'vault').glob('*.secret')))

    def test_mismatched_routing_rejected_before_secret_written(self):
        deployment = self.create_deployment()
        r = self.submit(deployment_id=deployment, target_model='different-alias')
        self.assertEqual(r.status_code,409)
        self.assertEqual(len(FakeTarget.sent),0)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM fingerprint_live_jobs').fetchone()[0], 0)

    def test_unlinked_jobs_keep_old_behavior(self):
        r = self.submit(target_model='gpt-test-id')
        self.assertEqual(r.status_code,202,r.text)
        self.assertIsNone(r.json()['deployment_id'])
        self.worker().run_once()
        result = self.client.get(f'/api/v1/fingerprint/live-jobs/{r.json()["job_id"]}',
                                 headers=self.headers()).json()
        self.assertIsNone(result['deployment_id'])
        self.assertEqual(result['result']['ui_result']['comparison']['status'], 'no_baseline')

    def test_missing_target_and_deployment_rejected_without_key_echo(self):
        r = self.submit()
        self.assertEqual(r.status_code,422)
        self.assertNotIn(KEY,r.text)
        self.assertNotIn(PROMPT,r.text)

    def test_use_stage1_still_rejected_even_with_baseline(self):
        dep = self.create_deployment()
        self.baseline(dep)
        r = self.submit(deployment_id=dep, use_stage1=True)
        self.assertEqual(r.status_code,409)
        self.assertNotIn(KEY,r.text)

    def test_owner_can_list_only_own_deployment_jobs(self):
        a = self.create_deployment()
        b = self.create_deployment(B)
        self.assertEqual(self.submit(deployment_id=a).status_code,202)
        self.assertEqual(self.submit(token=B,deployment_id=b).status_code,202)
        listed = self.client.get(f'/api/v1/deployments/{a}/jobs',
                                 headers=self.headers()).json()['jobs']
        self.assertEqual(len(listed),1)
        self.assertEqual(listed[0]['status'],'queued')

    def test_additive_migration_of_old_live_jobs(self):
        # Simulates an M4 row/table before the new columns were introduced.
        with sqlite3.connect(self.path) as con:
            # Re-create an old version of the table without M6 columns.
            con.execute('ALTER TABLE fingerprint_live_jobs RENAME TO old_live_jobs')
            con.execute('''CREATE TABLE fingerprint_live_jobs (
                job_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                started_at TEXT,finished_at TEXT,request_ciphertext TEXT,result_ciphertext TEXT,
                error_code TEXT,worker_id TEXT,attempt_count INTEGER NOT NULL DEFAULT 0)''')
            con.execute('DROP TABLE old_live_jobs')
            old_payload = self.crypto.seal({'prompt_text':'old queued prompt',
                                             'target_model':'gpt-existing-alias'})
            con.execute('''INSERT INTO fingerprint_live_jobs
                (job_id,owner_id,status,created_at,updated_at,expires_at,request_ciphertext)
                VALUES (?,?,?,?,?,?,?)''',
                ('pre-m6-job','alice','queued','2026-11-25T00:00:00+00:00',
                 '2026-11-25T00:00:00+00:00','2100-01-01T00:00:00+00:00',old_payload))
            con.commit()
        migrated = SqliteLiveJobStore(self.crypto,self.path)
        with sqlite3.connect(self.path) as con:
            names={row[1] for row in con.execute('PRAGMA table_info(fingerprint_live_jobs)')}
        self.assertTrue({'deployment_id','baseline_revision','baseline_id'} <= names)
        existing = migrated.get_for_owner('pre-m6-job','alice')
        self.assertEqual(existing['status'],'queued')
        self.assertIsNone(existing['deployment_id'])
        self.assertIsNone(existing['baseline_revision'])
        job,owner,payload = migrated.claim_next('migration-worker')
        self.assertEqual((job,owner),('pre-m6-job','alice'))
        self.assertEqual(payload['target_model'],'gpt-existing-alias')

    def test_ui_result_never_infers_identity_from_baseline(self):
        baseline = {'id':'a','revision':1,'model_id':'llama3.1-8b'}
        result = summarize_unvalidated_live_result(baseline)
        self.assertIsNone(result['identification']['accepted_model_id'])
        self.assertIsNone(result['comparison']['identity_change'])
        self.assertIsNone(result['model_card']['card'])


if __name__ == '__main__':
    unittest.main()
