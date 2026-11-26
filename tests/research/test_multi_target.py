"""Test per-negative-model confusion rates without fitting classifiers or using test data."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'system/research/stage1'))
from summarize_validation import create_reports


class MultiTargetReportsTests(unittest.TestCase):
    def test_negative_rates_counts_and_thresholds(self):
        models = ['model-a', 'model-b', 'model-c']
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / 'prepared'
            results = root / 'results'
            (data / 'summary.json').parent.mkdir(parents=True)
            (data / 'summary.json').write_text(json.dumps({'models': models}))
            records = []
            for model in models:
                for i in range(2):
                    records.append(dict(record_id=f'{model}-{i}', prompt_id=f'p{i}',
                        model_key=model, prompt_category='general', persona_id='P13', response_text=f'{model} response {i}'))
            for target in models:
                binary = pd.DataFrame([{**r,'label': int(r['model_key'] == target)} for r in records])
                dest = data / 'binary' / target / 'all_personas'
                dest.mkdir(parents=True)
                binary.to_csv(dest / 'validation.csv', index=False)
                pred = binary.drop(columns='response_text').copy()
                # model-a: 1/2 target false alarms, 1/2 B accepted, 0/2 C accepted at 0.5
                scores = ([0.8, 0.2, 0.7, 0.1, 0.3, 0.1] if target == 'model-a'
                          else [0.8 if r['model_key'] == target else 0.2 for r in records])
                pred['target_score'] = scores
                pred['predicted_target'] = (pred['target_score'] >= 0.5).astype(int)
                dest = results / target / 'all_personas'
                dest.mkdir(parents=True)
                pred.to_csv(dest / 'rf_stylometry_validation_predictions.csv', index=False)
                (dest / 'rf_stylometry_threshold.json').write_text(json.dumps({
                    'target_model': target, 'view': 'all_personas',
                    'algorithm':'rf_stylometry', 'threshold': 0.3}))
            out = root / 'comparison'
            output = create_reports(data, results, out, algorithms=('rf_stylometry',), require_all=True)
            rates = output['negatives']
            row_b = rates[(rates.target_model == 'model-a') & (rates.negative_model == 'model-b')
                          & (rates.threshold_rule == 'fixed_0.5')].iloc[0]
            row_c = rates[(rates.target_model == 'model-a') & (rates.negative_model == 'model-c')
                          & (rates.threshold_rule == 'fixed_0.5')].iloc[0]
            self.assertEqual(row_b['incorrectly_accepted'], 1)
            self.assertEqual(row_b['correctly_rejected'], 1)
            self.assertEqual(row_b['false_acceptance_rate'], 0.5)
            self.assertEqual(row_c['incorrectly_accepted'], 0)
            self.assertEqual(row_c['change_detection_rate'], 1.0)
            baseline = output['positives']
            row_target = baseline[(baseline.target_model == 'model-a') & (baseline.threshold_rule == 'fixed_0.5')].iloc[0]
            self.assertEqual(row_target['false_alarms'], 1)
            self.assertEqual(row_target['false_alarm_rate'], 0.5)
            matrix = pd.read_csv(out / 'negative_acceptance_matrix.csv')
            self.assertEqual(len(matrix), 6)  # 3 targets x 2 threshold rules
            self.assertEqual(len(pd.read_csv(out / 'all_validation_predictions.csv')), 36)

    def test_refuses_stale_predictions(self):
        models = ['model-a', 'model-b']
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); data = root / 'prepared'; result = root / 'results'
            data.mkdir(parents=True)
            (data / 'summary.json').write_text(json.dumps({'models': models}))
            binary = pd.DataFrame([
                dict(record_id='a', prompt_id='p1', model_key='model-a', label=1, response_text='a', prompt_category='general'),
                dict(record_id='b', prompt_id='p2', model_key='model-b', label=0, response_text='b', prompt_category='general'),
            ])
            dest = data / 'binary' / 'model-a' / 'all_personas'; dest.mkdir(parents=True)
            binary.to_csv(dest / 'validation.csv', index=False)
            saved = binary.copy(); saved.loc[0, 'record_id'] = 'old-a'; saved['target_score'] = [0.8,0.2]
            dest = result / 'model-a' / 'all_personas'; dest.mkdir(parents=True)
            saved.to_csv(dest / 'rf_stylometry_validation_predictions.csv', index=False)
            (dest / 'rf_stylometry_threshold.json').write_text(json.dumps({
                'target_model':'model-a','view':'all_personas','algorithm':'rf_stylometry','threshold':0.5}))
            with self.assertRaisesRegex(ValueError, 'Stale validation predictions'):
                create_reports(data, result, root / 'out', algorithms=('rf_stylometry',))


if __name__ == '__main__':
    unittest.main()
