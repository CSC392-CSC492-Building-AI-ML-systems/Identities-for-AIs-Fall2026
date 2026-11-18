"""Regression checks for installing this project as <repo>/system/."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SYSTEM = Path(__file__).resolve().parents[1]
REPO = SYSTEM.parent


class RepositoryRootLayoutTests(unittest.TestCase):
    def test_subsystem_files_are_contained_within_system(self):
        for name in ('TBD.md', 'README.md', 'catalog/models.json',
                     'models/registry.json', 'config/production.yaml',
                     'fingerprinting/eval_cli.py', 'run.py'):
            with self.subTest(name=name):
                self.assertTrue((SYSTEM / name).is_file())

    def test_config_launcher_works_from_parent_repo_root(self):
        call = subprocess.run(
            [sys.executable, 'system/run.py', 'config',
             'config/experiments/random_forest_only.yaml', '--require-ready'],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
        self.assertEqual(call.returncode, 0, call.stderr)
        result = json.loads(call.stdout)
        self.assertTrue(result['valid_configuration'])
        self.assertTrue(result['readiness']['ready'])

    def test_package_can_import_from_repo_root(self):
        call = subprocess.run(
            [sys.executable, '-c',
             'from system.fingerprinting.pipeline import FingerprintPipeline; print(FingerprintPipeline.__name__)'],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
        self.assertEqual(call.returncode, 0, call.stderr)
        self.assertEqual(call.stdout.strip(), 'FingerprintPipeline')


if __name__ == '__main__':
    unittest.main()
