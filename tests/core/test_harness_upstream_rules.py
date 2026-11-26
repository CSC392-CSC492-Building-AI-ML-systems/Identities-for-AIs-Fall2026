"""Execute the original Harness's own 18 rule/card/status regression tests."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=(Path(__file__).resolve().parents[2] / 'system')
AGENT=ROOT/'models/harness/v1/agent'


class UpstreamRuleSuiteTests(unittest.TestCase):
    def test_original_harness_rule_suite(self):
        result=subprocess.run([sys.executable,'test_rules.py'],cwd=AGENT,
                              capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,(result.stdout+'\n'+result.stderr)[-1400:])
        self.assertIn('18/18 unit tests passed',result.stdout)
