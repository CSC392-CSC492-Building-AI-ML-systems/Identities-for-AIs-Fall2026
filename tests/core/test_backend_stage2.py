"""Stage 2 prototype: actual trained RF with replayed target answers; no external calls."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from system.backend.app import create_app
from system.backend.history_store import HistoryStore
from system.backend.jobs.live_store import SqliteLiveJobStore
from system.backend.jobs.live_runner import LiveJobWorker
from system.backend.security.crypto import LiveCrypto, FileSecretVault
from system.backend.security.auth import LocalTokenAuth
from system.backend.services.stage2 import make_stage2_gateway, ROOT, NoRetryTargetClient
from system.backend.services.analysis import make_mock_gateway
from system.backend.services.live import LiveOpenAIAnalysisGateway
from system.backend.ui_results import summarize_stage2_result
from system.fingerprinting.schemas import ProbeQuestion, IdentificationResult

TOKEN = 'demo-token-' * 8
OTHER = 'other-token-' * 8
KEY = 'PRIVATE_PROVIDER_TEST_KEY'
PROMPT = 'Private initial prompt sentinel'


class Stage2BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calls = []
        cls.closed = []
        cls.answers = {}
        def provider_factory(key, model):
            class FakeTarget:
                def send_prompt(self, prompt):
                    cls.calls.append(prompt)
                    return cls.answers.get(prompt, 'Example initial answer.')
                def close(self):
                    cls.closed.append(True)
            return FakeTarget()
        cls.gateway = make_stage2_gateway(provider_factory=provider_factory)
        probes = cls.gateway.workflow.pipeline.stage2.identifiers[0].required_probes()
        data = ROOT / 'datasets/collector_raw/agentic-2026-11-26/raw/claude-haiku-4.5/fingerprint_v0.jsonl'
        records = [json.loads(line) for line in data.read_text(encoding='utf-8').splitlines()]
        for p in probes:
            row = next(r for r in records if r['prompt_id']==p.probe_id and r['persona_id']=='BK4' and r['sample_index']==0 and not r.get('error') and (r.get('response_text') or '').strip())
            cls.answers[p.prompt_text] = row['response_text']
            assert cls.answers[p.prompt_text].strip()

    def setUp(self):
        self.calls.clear(); self.closed.clear()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = SqliteLiveJobStore(LiveCrypto(Fernet.generate_key()),root/'jobs.sqlite3')
        self.vault = FileSecretVault(self.store.crypto,root/'vault')
        self.history = HistoryStore(self.store.path)
        auth = LocalTokenAuth({u:hashlib.sha256(t.encode()).hexdigest() for u,t in [('alice',TOKEN),('bob',OTHER)]})
        self.mock = make_mock_gateway()
        self.client = TestClient(create_app(self.mock, token_auth=auth, live_job_store=self.store,
            secret_vault=self.vault,history_store=self.history))
        self.headers = {'Authorization':f'Bearer {TOKEN}'}

    def tearDown(self):
        self.client.close(); self.tmp.cleanup()

    def submit(self, **extra):
        return self.client.post('/api/v1/fingerprint/live-jobs',headers=self.headers,json={
            'prompt_text':PROMPT,'api_key':KEY,'target_model':'not-ground-truth',
            'mode':'live_stage2_review',**extra})

    def worker(self, **kwargs):
        return LiveJobWorker(self.store,self.vault,self.gateway,mode='live_stage2_review',**kwargs)

    def poll(self,job):
        r=self.client.get('/api/v1/fingerprint/live-jobs/'+job,headers=self.headers)
        self.assertEqual(r.status_code,200,r.text); return r.json()

    def test_real_rf_through_http_and_worker(self):
        r=self.submit(); self.assertEqual(r.status_code,202,r.text)
        job=r.json()['job_id']
        self.assertEqual(r.json()['mode'],'live_stage2_review')
        self.assertIsNone(self.store.claim_next('legacy-worker'))
        self.assertEqual(self.worker().run_once(),job)
        d=self.poll(job); self.assertEqual(d['status'],'completed',d)
        self.assertEqual(d['mode'],'live_stage2_review')
        result=d['result']; v=result['ui_result']
        self.assertEqual(result['status'],'needs_review')
        self.assertIsNone(result['model_id']); self.assertFalse(result['stage1_enabled'])
        self.assertEqual(len(self.calls),7); self.assertEqual(len(set(self.calls)),7)
        self.assertEqual(len(result['target_queries']),7)
        self.assertEqual(len(self.closed),1)
        rows={x['method']:x for x in v['method_candidates']}
        self.assertEqual(rows['lora']['status'],'not_configured')
        self.assertEqual(rows['harness']['status'],'mock_judge')
        self.assertIsNone(rows['harness']['candidate_model_id'])
        self.assertEqual(rows['random_forest']['status'],'candidate')
        self.assertEqual(rows['random_forest']['artifact_id'],'random_forest/v2')
        self.assertEqual(len(rows['random_forest']['probe_ids_used']),5)
        self.assertEqual(v['candidate_agreement'],'single_candidate')
        self.assertIsNone(v['identification']['accepted_model_id'])
        self.assertNotIn(KEY,str(d)); self.assertNotIn(PROMPT,str(d))
        self.assertFalse(list(self.vault.folder.glob('*.secret')))
        self.assertEqual(self.client.get('/api/v1/fingerprint/live-jobs/'+job,
            headers={'Authorization':f'Bearer {OTHER}'}).status_code,404)

    def test_linked_review_job_never_updates_history(self):
        r=self.client.post('/api/v1/deployments',headers=self.headers,json={
            'label':'Demo deployment','provider':'openai','requested_model_id':'not-ground-truth'})
        self.assertEqual(r.status_code,201,r.text); dep=r.json()['id']
        r=self.client.post(f'/api/v1/deployments/{dep}/baselines',headers=self.headers,json={
            'model_id':'llama3.1-8b','acknowledge_manual_review':True,
            'review_note':'Reviewed demonstration baseline'})
        self.assertEqual(r.status_code,201,r.text)
        r=self.submit(deployment_id=dep); self.assertEqual(r.status_code,202,r.text)
        job=r.json()['job_id']; self.worker().run_once()
        result=self.poll(job)['result']; view=result['ui_result']
        self.assertEqual(view['comparison']['status'],'insufficient_evidence')
        self.assertEqual(view['baseline']['revision'],1)
        self.assertIsNone(view['comparison']['current_model_id'])
        self.assertFalse(view['evidence']['baseline_auto_updated'])
        self.assertEqual(len(self.history.list_history('alice',dep)),1)

    def test_external_judge_gateway_uses_pinned_harness(self):
        gateway=make_stage2_gateway(live_judge=True)
        self.assertEqual(gateway.judge,'google')
        harness=gateway.workflow.pipeline.stage2.identifiers[0]
        self.assertIsNone(harness._runner)
        self.assertTrue(harness.review_only)

    def test_consent_requires_configured_judge_before_target_calls(self):
        r=self.submit(allow_live_judge=True); self.assertEqual(r.status_code,202)
        job=r.json()['job_id']; self.worker().run_once()
        self.assertEqual(self.poll(job)['error_code'],'JUDGE_NOT_CONFIGURED')
        self.assertEqual(self.calls,[]); self.assertFalse(list(self.vault.folder.glob('*.secret')))

    def test_consent_invalid_for_legacy(self):
        self.assertEqual(self.submit(mode='live_target_mock_judge',allow_live_judge=True).status_code,422)

    def test_stage1_rejected(self):
        self.assertEqual(self.submit(use_stage1=True).status_code,409)

    def test_queue_modes_separate(self):
        r=self.submit(mode='live_target_mock_judge'); self.assertEqual(r.status_code,202)
        self.assertIsNone(self.worker().run_once())
        self.assertEqual(self.poll(r.json()['job_id'])['status'],'queued')

    def test_no_retry_after_failed_probe(self):
        calls=[]
        def failure(text):
            calls.append(text); raise RuntimeError('network error')
        c=NoRetryTargetClient(failure)
        for _ in range(2):
            with self.assertRaises(RuntimeError): c.ask(ProbeQuestion('P','question'))
        self.assertEqual(calls,['question'])

    def test_old_lora_unpinned_rejected_before_calls(self):
        with self.assertRaises(ValueError):
            make_stage2_gateway(ROOT/'config/production.yaml')

    def test_mock_judge_cannot_be_candidate_and_raw_reason_not_exposed(self):
        report=self.gateway.analyze(PROMPT,api_key=KEY,target_model='alias')
        attempts=[IdentificationResult('harness','unknown',candidate_model_id='claude-haiku-4.5',score=1.0,score_type='fit_score',reason=KEY)]
        report=replace(report,fingerprint=replace(report.fingerprint,stage2_attempts=attempts))
        v=summarize_stage2_result(report,None,self.gateway.workflow.catalog,'mock')
        self.assertEqual(v['method_candidates'][1]['status'],'mock_judge')
        self.assertIsNone(v['method_candidates'][1]['candidate_model_id']); self.assertNotIn(KEY,str(v))

    def test_explicit_live_judge_selection_isolated(self):
        class GatewaySpy:
            judge='google'
            workflow=self.gateway.workflow
            def analyze(inner,*args,**kwargs):
                return self.gateway.analyze(*args,**kwargs)
        spy=GatewaySpy()
        with patch.object(spy,'analyze',wraps=spy.analyze) as call:
            for consent in (False,True):
                r=self.submit(allow_live_judge=consent); self.assertEqual(r.status_code,202)
                self.worker(live_judge_gateway=spy).run_once()
                v=self.poll(r.json()['job_id'])['result']['ui_result']
                self.assertEqual(v['evidence']['judge'],'google' if consent else 'mock')
            self.assertEqual(call.call_count,1)

if __name__=='__main__': unittest.main()
