"""Smoke checks for consolidation, prompt splitting, labels, features and scoring.

Run: python -m unittest discover -s tests -v
"""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from stylometry import features_for_text, FEATURE_NAMES
from metrics_common import threshold_for_false_alarm_limit


class PipelineTests(unittest.TestCase):
    def test_stylometric_features(self):
        vals = features_for_text('## Heading\n\n- A point.\n- Another point!')
        self.assertEqual(len(vals), len(FEATURE_NAMES))
        self.assertGreater(vals[FEATURE_NAMES.index('headings')], 0)
        self.assertGreater(vals[FEATURE_NAMES.index('bullet_lines')], 0)

    def test_threshold_definition(self):
        threshold = threshold_for_false_alarm_limit([1] * 10 + [0] * 10,
                                                     [x / 10 for x in range(10)] + [0.2] * 10,
                                                     0.1)
        self.assertEqual(threshold, 0.1)

    def test_consolidation_binary_labels_and_no_leakage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / 'raw'
            prompt_csv = root / 'prompts.csv'
            with prompt_csv.open('w', encoding='utf-8', newline='') as f:
                w = csv.writer(f)
                w.writerow(['', 'sample title'])
                w.writerow(['source_id', 'text', 'category', 'persona_id', 'group'])
                for i in range(20):
                    w.writerow([f'p{i:02}', f'Explain sample number {i}', 'general', 'P13', 'test'])
            for model in ['model-a', 'model-b']:
                dest = raw / model
                dest.mkdir(parents=True)
                with (dest / 'training_v1.jsonl').open('w', encoding='utf-8') as f:
                    for i in range(20):
                        row = {'record_id': f'{model}-{i}', 'prompt_id': f'p{i:02}',
                               'model_key': model, 'persona_id': 'P13',
                               'response_text': f'Example response {i} from {model}.'}
                        f.write(json.dumps(row) + '\n')
            out = root / 'prepared'
            subprocess.run([sys.executable, str(SCRIPTS / 'prepare_supervised_data.py'),
                            '--raw-dir', str(raw), '--prompts', str(prompt_csv), '--out', str(out),
                            '--expected-models', '2', '--seed', '42'], check=True, capture_output=True)
            import pandas as pd
            chunks = {n: pd.read_csv(out / 'binary' / 'model-a' / 'all_personas' / f'{n}.csv')
                      for n in ['development', 'validation', 'test']}
            self.assertEqual(sum(len(x) for x in chunks.values()), 40)
            for left, right in [('development', 'validation'), ('development', 'test'), ('validation', 'test')]:
                self.assertFalse(set(chunks[left].prompt_id) & set(chunks[right].prompt_id))
            for df in chunks.values():
                self.assertTrue((df['label'] == (df['model_key'] == 'model-a').astype(int)).all())
                self.assertTrue(df['prompt_text'].str.startswith('Explain sample').all())


if __name__ == '__main__':
    unittest.main()
