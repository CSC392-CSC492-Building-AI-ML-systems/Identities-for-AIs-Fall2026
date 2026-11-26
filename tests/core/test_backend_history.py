"""M5 tests: owner scoping, immutable reviewed history, real API contracts."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from system.backend.app import create_app
from system.backend.history_store import HistoryStore
from system.backend.cards_repository import RepositoryCards, field_changes
from system.backend.security.auth import LocalTokenAuth
from system.backend.services.analysis import make_mock_gateway
from system.fingerprinting.model_catalog import ModelCatalog

A, B = 'secret-test-A' * 8, 'secret-test-B' * 8


def card(model, value='alpha', source='https://example.org/a'):
    return {'model_key': model, 'name':model, 'family':'Llama', 'confirmed':True,
            'domains':[{'domain':'risk', 'title':'Risk', 'fields':[
                {'id':'risk_level','name':'Risk Level','value':value,'source':source},
                {'id':'missing','name':'Missing','value':'Unknown','missing':True}]}]}


class FakeCards:
    def __init__(self):
        self.cards = {'llama3.1-8b':card('llama3.1-8b', 'one'),
                      'llama3.2-3b':card('llama3.2-3b', 'two')}
    def get(self, model):
        return self.cards.get(model)


class BackendHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = HistoryStore(self.root/'jobs.sqlite3')
        self.cards = FakeCards()
        auth = LocalTokenAuth({'alice':hashlib.sha256(A.encode()).hexdigest(),
                               'bob':hashlib.sha256(B.encode()).hexdigest()})
        self.client = TestClient(create_app(make_mock_gateway(), token_auth=auth,
                                            history_store=self.store, repository_cards=self.cards))
    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()
    def h(self, tok=A):
        return {'Authorization':f'Bearer {tok}'}
    def deployment(self, token=A):
        r=self.client.post('/api/v1/deployments', headers=self.h(token),
                           json={'label':'Monitored GPT alias', 'provider':'openai',
                                 'requested_model_id':'gpt-alias-prod'})
        self.assertEqual(r.status_code,201,r.text)
        return r.json()['id']
    def baseline(self, dep, model='llama3.1-8b', token=A, **extra):
        return self.client.post(f'/api/v1/deployments/{dep}/baselines',headers=self.h(token),
            json={'model_id':model,'acknowledge_manual_review':True,
                  'review_note':'Reviewed by researcher with external evidence',**extra})

    def test_auth_required_all_history_endpoints(self):
        self.assertEqual(self.client.post('/api/v1/deployments',json={'label':'x','requested_model_id':'q'}).status_code,401)
        for uri in ['/api/v1/models/llama3.1-8b/card','/api/v1/deployments',
                    '/api/v1/deployments/abc/history','/api/v1/deployments/abc/changes']:
            self.assertEqual(self.client.get(uri).status_code,401)

    def test_create_list_deployments_and_owner_isolation(self):
        dep=self.deployment()
        self.assertEqual(len(self.client.get('/api/v1/deployments',headers=self.h()).json()['deployments']),1)
        self.assertEqual(self.client.get(f'/api/v1/deployments/{dep}',headers=self.h(B)).status_code,404)
        self.assertEqual(self.client.get(f'/api/v1/deployments/{dep}/history',headers=self.h(B)).status_code,404)
        self.assertEqual(self.client.get(f'/api/v1/deployments/{dep}/changes',headers=self.h(B)).status_code,404)
        self.assertEqual(len(self.client.get('/api/v1/deployments',headers=self.h(B)).json()['deployments']),0)

    def test_manually_approved_baselines_are_append_only_and_hashed(self):
        dep=self.deployment()
        first=self.baseline(dep).json()
        self.assertEqual(first['confirmation_source'],'manual_review')
        self.assertEqual(first['revision'],1)
        snapshot=first['card_snapshot']
        self.assertEqual(first['card_snapshot_sha256'],hashlib.sha256(json.dumps(snapshot,
                 sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
        self.cards.cards['llama3.1-8b']=card('llama3.1-8b','updated')
        second=self.baseline(dep).json()
        self.assertEqual(second['revision'],2)
        saved=self.client.get(f'/api/v1/deployments/{dep}/history',headers=self.h()).json()['history']
        self.assertEqual(saved[0]['card_snapshot']['domains'][0]['fields'][0]['value'],'one')
        self.assertEqual(saved[1]['card_snapshot']['domains'][0]['fields'][0]['value'],'updated')
        self.assertNotEqual(saved[0]['card_snapshot_sha256'],saved[1]['card_snapshot_sha256'])

    def test_model_and_card_differences(self):
        dep=self.deployment()
        self.assertEqual(self.client.get(f'/api/v1/deployments/{dep}/changes',headers=self.h()).json()['status'],'no_baseline')
        self.baseline(dep)
        self.assertEqual(self.client.get(f'/api/v1/deployments/{dep}/changes',headers=self.h()).json()['status'],'no_previous_baseline')
        self.baseline(dep,model='llama3.2-3b')
        change=self.client.get(f'/api/v1/deployments/{dep}/changes',headers=self.h()).json()
        self.assertEqual(change['status'],'manual_reviewed_comparison')
        self.assertTrue(change['identity_change'])
        self.assertFalse(change['family_change'])
        self.assertEqual(change['card_comparison']['status'],'compared')
        self.assertEqual(change['card_comparison']['changes'][0]['field_id'],'risk_level')
        self.assertEqual(change['card_comparison']['changes'][0]['after_value'],'two')
        self.assertEqual(change['evidence_status'],'manual_reviewed_history_only')

    def test_cross_family_change(self):
        self.cards.cards['qwen3-8b']=card('qwen3-8b','other')
        dep=self.deployment()
        self.baseline(dep)
        self.baseline(dep,model='qwen3-8b')
        report=self.client.get(f'/api/v1/deployments/{dep}/changes',headers=self.h()).json()
        self.assertTrue(report['family_change'])
        self.assertEqual(report['after_family_id'],'qwen')

    def test_model_card_endpoint_and_unknown_model(self):
        r=self.client.get('/api/v1/models/llama3.1-8b/card',headers=self.h())
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['card']['model_key'],'llama3.1-8b')
        self.assertEqual(r.json()['status'],'available')
        missing=self.client.get('/api/v1/models/gpt-6.1-terra/card',headers=self.h())
        self.assertEqual(missing.json()['status'],'unavailable')
        self.assertEqual(self.client.get('/api/v1/models/NOT_A_MODEL/card',headers=self.h()).status_code,404)

    def test_cannot_auto_promote_candidate_or_skip_confirmation(self):
        dep=self.deployment()
        for body in [
            {'model_id':'llama3.1-8b','acknowledge_manual_review':False,'review_note':'Reviewed by research team'},
            {'model_id':'llama3.1-8b','acknowledge_manual_review':True,'review_note':'short'},
            {'model_id':'llama3.1-8b','acknowledge_manual_review':True,'review_note':'Reviewed by research team','candidate_model_id':'qwen3-8b'},
            {'model_id':'qwen-unknown','acknowledge_manual_review':True,'review_note':'Reviewed by research team'},
        ]:
            r=self.client.post(f'/api/v1/deployments/{dep}/baselines',headers=self.h(),json=body)
            self.assertIn(r.status_code,(404,422),r.text)
        self.assertEqual(self.client.get(f'/api/v1/deployments/{dep}/history',headers=self.h()).json()['history'],[])

    def test_cross_user_cannot_write_another_baseline(self):
        dep=self.deployment()
        self.assertEqual(self.baseline(dep,token=B).status_code,404)
        self.assertEqual(self.client.get(f'/api/v1/deployments/{dep}/history',headers=self.h()).json()['history'],[])

    def test_missing_cards_still_allow_manual_identity_with_unavailable_card(self):
        dep=self.deployment()
        saved=self.baseline(dep,model='gpt-6.1-terra').json()
        self.assertEqual(saved['card_status'],'unavailable')
        self.assertIsNone(saved['card_snapshot_sha256'])
        self.baseline(dep)
        changes=self.client.get(f'/api/v1/deployments/{dep}/changes',headers=self.h()).json()
        self.assertEqual(changes['card_comparison']['status'],'card_unavailable')

    def test_history_persists_after_restart(self):
        dep=self.deployment()
        self.baseline(dep)
        second_store=HistoryStore(self.root/'jobs.sqlite3')
        self.assertEqual(second_store.get_deployment('alice',dep)['baseline']['revision'],1)
        self.assertEqual(second_store.list_history('alice',dep)[0]['model_id'],'llama3.1-8b')

    def test_card_field_diff_separates_sources(self):
        result=field_changes(card('llama3.1-8b',source='url1'),card('llama3.1-8b',source='url2'))
        self.assertEqual(len(result['changes']),1)
        self.assertFalse(result['changes'][0]['value_changed'])
        self.assertTrue(result['changes'][0]['source_changed'])
        self.assertEqual(field_changes(None,card('llama3.1-8b'))['status'],'card_unavailable')

    def test_cardlib_is_loaded_from_sibling_repo(self):
        # Tiny temporary implementation proves path routing and missing handling.
        cards=self.root/'cards'
        cards.mkdir()
        (cards/'cardlib.py').write_text('def build_card(model_key):\n'
            '    if model_key == "unavailable": raise KeyError(model_key)\n'
            '    return {"model_key":model_key,"domains":[]}\n')
        svc=RepositoryCards(self.root)
        self.assertEqual(svc.get('llama3.1-8b')['model_key'],'llama3.1-8b')
        self.assertIsNone(svc.get('unavailable'))

    def test_rejected_api_key_never_in_response_or_db(self):
        dep=self.deployment()
        secret='FAKE_CREDENTIAL_SENTINEL_d4e30e'
        r=self.client.post(f'/api/v1/deployments/{dep}/baselines',headers=self.h(),json={
            'model_id':'llama3.1-8b','acknowledge_manual_review':True,
            'review_note':'Reviewed by researcher','api_key':secret})
        self.assertEqual(r.status_code,422)
        self.assertNotIn(secret,r.text)
        self.assertNotIn(secret.encode(),(self.root/'jobs.sqlite3').read_bytes())


if __name__=='__main__':
    unittest.main()
