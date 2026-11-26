from __future__ import annotations
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import yaml
from fingerprinting.onboarding import identities as i

class IdentityOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.repo=Path(self.tmp.name);self.root=self.repo/'system';self.cp=self.root/'catalog/models.json';self.mp=self.root/'collector/models.yaml';self.cards=self.repo/'cards'
        self.cp.parent.mkdir(parents=True);self.mp.parent.mkdir();self.cards.mkdir()
        for script in ('new_model.py','cardlib.py','check_cards.py'): (self.cards/script).touch()
        for d in i.DOMAINS:
            f=self.cards/'fields'/f'{d}.yaml';f.parent.mkdir(exist_ok=True);f.write_text('fields: []\n')
        self.original={'schema_version':'1.0','models':{'old-1':{'family_id':'old','developer':'Old Developer','display_name':'Old 1','provider':'ollama','provider_model_id':'old:1'}}}
        self.cp.write_text(json.dumps(self.original));self.mp.write_text('# existing comment\nmodels:\n  - {model_key: old-1, provider: ollama, model_id: "old:1", enabled: true}\n')
        self.s={'model_id':'new-1','family_id':'new','family_name':'New','developer':'New Developer','display_name':'New 1','provider':'ollama','provider_model_id':'new:1','access':'open','identity_source':'https://example.org/documentation','researched_by':'Researcher'}
    def validated(self,**kwargs):
        p=self.repo/'spec.json';p.write_text(json.dumps({**self.s,**kwargs}));return i.spec_load(p)
    def register(self): return i.register(self.root,self.s,True)
    def fake_cards(self,cards,job):
        if job['action']=='draft':
            a=job['args'];return {d:yaml.safe_dump({'model_key':a['model_key'],'name':a['name'],'family':a['family'],'access':a['access'],'researched_by':a['by'],'domain':d,'fields':{'example':{'value':'TODO','source':'TODO'}}}) for d in job['domains']}
        return {d:{'errors':[],'todos':['example'] if 'TODO' in Path(p).read_text() else []} for d,p in job['paths'].items()}
    def test_plan_is_read_only_and_new_family_requires_permission(self):
        before=(self.cp.read_bytes(),self.mp.read_bytes())
        with self.assertRaises(ValueError):i.plan(self.root,self.s)
        self.assertTrue(i.plan(self.root,self.s,True)['new_family']);self.assertEqual(before,(self.cp.read_bytes(),self.mp.read_bytes()))
    def test_registration_append_and_disabled_preserves_previous_entries(self):
        old=self.mp.read_bytes();r=self.register();self.assertEqual(r['status'],'registered');self.assertTrue(self.mp.read_bytes().startswith(old));self.assertFalse(i.collector(self.mp)[1]['new-1']['enabled']);self.assertEqual(i.read_json(self.cp)['models']['old-1'],self.original['models']['old-1']);self.assertEqual(self.register()['status'],'unchanged')
    def test_existing_family_new_model(self):
        s={**self.s,'family_id':'old','family_name':'Old','developer':'Old Developer'};self.assertFalse(i.plan(self.root,s)['new_family']);i.register(self.root,s)
    def test_family_developer_conflict(self):
        with self.assertRaises(ValueError):i.plan(self.root,{**self.s,'family_id':'old','family_name':'Old'})
    def test_duplicate_route_and_label(self):
        for change in ({'provider_model_id':'old:1'},{'display_name':'OLD 1'}):
            with self.subTest(change=change),self.assertRaises(ValueError):i.plan(self.root,{**self.s,**change},True)
    def test_existing_id_cannot_be_changed(self):
        self.register()
        with self.assertRaises(ValueError):i.register(self.root,{**self.s,'display_name':'Edited'},True)
    def test_spec_unsafe_or_unavailable_transport(self):
        for change in ({'model_id':'../evil'},{'model_id':'con'},{'provider':'unknown'},{'family_name':'Mismatch'},{'provider_model_id':'TODO-confirm'},{'identity_source':'file:///local'}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.validated(**change)
    def test_missing_collector_entry_backfilled_without_changing_catalog(self):
        self.register();old=self.cp.read_bytes();self.mp.write_text('# existing comment\nmodels:\n  - {model_key: old-1, provider: ollama, model_id: "old:1", enabled: true}\n');i.register(self.root,self.s);self.assertEqual(old,self.cp.read_bytes())
    def test_duplicate_collector_key_refused(self):
        self.mp.write_text(self.mp.read_text()+'  - {model_key: old-1, provider: ollama, model_id: old:2}\n')
        with self.assertRaises(ValueError):i.plan(self.root,self.s,True)
    def test_conflicting_collector_entry_refused(self):
        self.mp.write_text(self.mp.read_text()+'  - {model_key: new-1, provider: ollama, model_id: TODO-confirm}\n')
        with self.assertRaises(ValueError):i.plan(self.root,self.s,True)
    @patch.object(i,'card_call',autospec=True)
    def test_drafts_outside_cards_and_publication_guard(self,call):
        call.side_effect=self.fake_cards;self.register();r=i.draft(self.root,self.s);self.assertEqual(len(r['created_domains']),4);self.assertFalse((self.cards/'data').exists());out=Path(r['draft_directory']);p=out/'risk/new-1.yaml';p.write_text(p.read_text().replace('TODO','reviewed'));before=p.read_bytes();i.draft(self.root,self.s);self.assertEqual(before,p.read_bytes())
        with self.assertRaises(ValueError):i.publish_cards(self.root,self.s)
        self.assertFalse((self.cards/'data').exists())
        for p in out.glob('*/*.yaml'):p.write_text(p.read_text().replace('TODO','reviewed'))
        self.assertEqual(i.publish_cards(self.root,self.s)['status'],'published');self.assertEqual(i.publish_cards(self.root,self.s)['status'],'unchanged')
    def test_draft_requires_registration(self):
        with self.assertRaises(ValueError):i.draft(self.root,self.s)
    def test_concurrent_file_change_preflight(self):
        old=self.cp.read_bytes();self.cp.write_bytes(old+b'\n');before=self.mp.read_bytes()
        with self.assertRaises(ValueError):i.commit({self.mp:(before,b'new'),self.cp:(old,b'new')})
        self.assertEqual(self.mp.read_bytes(),before)
    def test_existing_lock_refuses_writer(self):
        with i.lock(self.root):
            with self.assertRaises(FileExistsError):self.register()

if __name__=='__main__':unittest.main()
