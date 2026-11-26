"""C1 cleanup regression tests: Stage 1 lives; original scripts stay outside system/."""
from pathlib import Path
import json
import tempfile
import unittest

from tools.apply_c1_cleanup import CleanupRefused, cleanup

SYSTEM_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SYSTEM_ROOT.parent

class Stage1DedupTests(unittest.TestCase):
    def test_no_embedded_research_scripts(self):
        self.assertFalse((SYSTEM_ROOT / 'reference_stage1' / 'scripts').exists())

    def test_stage1_manifest_keeps_all_artifact_files(self):
        m = json.loads((SYSTEM_ROOT/'models/stage1_lr/v1/manifest.json').read_text())
        self.assertEqual(m['artifact_id'], 'stage1_lr/v1')
        self.assertEqual(len(m['required_files']), 19)
        self.assertEqual(m['stage'], 1)

    def test_root_parity_source_when_checkout_available(self):
        src = REPO_ROOT / 'scripts'
        if not src.is_dir():
            self.skipTest('Standalone system/ distribution; root research scripts are external')
        self.assertTrue((src/'predict_hierarchical.py').is_file())
        self.assertTrue((src/'train_hierarchical.py').is_file())

class CheckedMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo/'scripts').mkdir()
        (self.repo/'system/reference_stage1/scripts').mkdir(parents=True)
        (self.repo/'scripts/predict_hierarchical.py').write_text('original', encoding='utf-8')
        (self.repo/'system/reference_stage1/scripts/predict_hierarchical.py').write_text('original', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_checked_dry_run_keeps_original_and_copy(self):
        self.assertEqual(cleanup(self.repo), ['predict_hierarchical.py'])
        self.assertTrue((self.repo/'system/reference_stage1/scripts/predict_hierarchical.py').exists())

    def test_checked_apply_deletes_only_duplicate_copy(self):
        removed = cleanup(self.repo, apply=True)
        self.assertEqual(removed, ['predict_hierarchical.py'])
        self.assertTrue((self.repo/'scripts/predict_hierarchical.py').exists())
        self.assertFalse((self.repo/'system/reference_stage1/scripts').exists())
        self.assertEqual(cleanup(self.repo, apply=True), [])

    def test_differing_copy_is_not_deleted(self):
        (self.repo/'system/reference_stage1/scripts/predict_hierarchical.py').write_text('modified')
        with self.assertRaisesRegex(CleanupRefused, 'differs'):
            cleanup(self.repo, apply=True)
        self.assertTrue((self.repo/'system/reference_stage1/scripts/predict_hierarchical.py').exists())

    def test_preflight_refuses_partial_cleanup_when_one_file_diverged(self):
        (self.repo/'scripts/train_hierarchical.py').write_text('original')
        (self.repo/'system/reference_stage1/scripts/train_hierarchical.py').write_text('modified')
        with self.assertRaisesRegex(CleanupRefused, 'differs'):
            cleanup(self.repo, apply=True)
        # The first otherwise-valid copy must not have been deleted either.
        self.assertTrue((self.repo/'system/reference_stage1/scripts/predict_hierarchical.py').exists())

    def test_extra_unapproved_file_is_preserved(self):
        (self.repo/'system/reference_stage1/scripts/teammate_notes.txt').write_text('keep')
        cleanup(self.repo, apply=True)
        self.assertTrue((self.repo/'system/reference_stage1/scripts/teammate_notes.txt').exists())


if __name__ == '__main__':
    unittest.main()
