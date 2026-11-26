from __future__ import annotations
import hashlib, tempfile, unittest,sys
from pathlib import Path
sys.path.insert(0,str((Path(__file__).resolve().parents[2] / 'system')/'tools'))
from apply_legacy_cleanup import cleanup

class CleanupTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.repo=Path(t.name);(self.repo/'system').mkdir()
        self.inv={}
        for group,rel in [('legacy','legacy'),('supervised','collector/data/supervised')]:
            path=self.repo/rel/'sample.txt';path.parent.mkdir(parents=True);path.write_bytes(b'old')
            self.inv[group]={'directory':rel,'files':[{'path':rel+'/sample.txt','bytes':3,'sha256':hashlib.sha256(b'old').hexdigest()}]}
        self.raw=self.repo/'collector/data/raw/active.jsonl';self.raw.parent.mkdir();self.raw.write_bytes(b'active')
        self.active=self.repo/'system/model.bin';self.active.write_bytes(b'active')
    def call(self,groups,**kwargs):return cleanup(self.repo,groups,inventory=self.inv,**kwargs)
    def test_preview_and_apply_legacy(self):
        self.assertEqual(self.call(['legacy'])['groups'][0]['matched_files'],1);self.assertTrue((self.repo/'legacy').exists())
        self.call(['legacy'],apply=True);self.assertFalse((self.repo/'legacy').exists());self.assertTrue(self.raw.exists());self.assertTrue(self.active.exists())
    def test_derived_requires_confirmation(self):
        with self.assertRaisesRegex(ValueError,'confirm-inactive'):self.call(['supervised'],apply=True)
        self.call(['supervised'],apply=True,confirm_inactive=True);self.assertTrue(self.raw.exists());self.assertTrue(self.active.exists())
    def test_modified_or_extra_refused_before_any_deletion(self):
        p=self.repo/'collector/data/supervised/sample.txt';p.write_bytes(b'new')
        with self.assertRaisesRegex(ValueError,'Modified'):self.call(['legacy','supervised'],apply=True,confirm_inactive=True)
        self.assertTrue((self.repo/'legacy/sample.txt').exists());p.write_bytes(b'old');(p.parent/'new.txt').write_text('new')
        with self.assertRaisesRegex(ValueError,'Unreviewed'):self.call(['legacy','supervised'],apply=True,confirm_inactive=True)
        self.assertTrue((self.repo/'legacy/sample.txt').exists())
    def test_missing_files_are_noop(self):
        self.call(['legacy'],apply=True);self.assertEqual(self.call(['legacy'],apply=True)['groups'][0]['matched_files'],0)
if __name__=='__main__':unittest.main()
