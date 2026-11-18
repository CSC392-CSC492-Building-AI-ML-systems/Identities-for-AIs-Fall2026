"""Tests for within-family selection and exact-record comparison."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from train_within_family import select_pair, per_prompt_ranking, FAMILIES
from compare_with_ovr import joined_pair, per_prompt_stats

class WithinFamilyTests(unittest.TestCase):
    def example_data(self):
        rows=[]
        for pi in range(3):
            for m in ['gemini-3.1-pro','gemini-3.8-flash','llama3.1-8b','llama3.2-3b']:
                rows.append({'prompt_id':f'p{pi}', 'record_id':f'{m}-{pi}',
                             'model_key':m,'response_text':m,'prompt_category':'general',
                             'persona_id':'P13'})
        return pd.DataFrame(rows)

    def test_same_family_only_and_labels(self):
        df=self.example_data()
        for family,(target,sibling) in FAMILIES.items():
            subset=select_pair(df,target,sibling)
            self.assertEqual(len(subset),6)
            self.assertEqual(set(subset.model_key),{target,sibling})
            self.assertTrue((subset.label==(subset.model_key==target).astype(int)).all())

    def test_prompt_aggregates(self):
        df=select_pair(self.example_data(),'llama3.1-8b','llama3.2-3b')
        scores=np.where(df.label==1,.8,.2)
        rank=per_prompt_ranking(df,scores,'llama','llama3.1-8b','llama3.2-3b','lr_tfidf')
        self.assertEqual(len(rank),3)
        self.assertTrue((rank.target_ranked_higher==1).all())
        self.assertAlmostEqual(rank.score_margin.mean(),.6)

    def test_stale_predictions_rejected(self):
        df=select_pair(self.example_data(),'gemini-3.1-pro','gemini-3.8-flash')
        df=df.assign(family='gemini',sibling_model='gemini-3.8-flash',
                     target_model='gemini-3.1-pro',algorithm='lr_tfidf',
                     threshold_rule='fixed_0.5',target_score=0.5,threshold=.5)
        pair,old=joined_pair(df,df.copy())
        self.assertEqual(len(pair),6)
        stale=df.copy()
        stale.loc[stale.index[0],'record_id']='different-id'
        with self.assertRaisesRegex(ValueError,'Prediction datasets disagree'):
            joined_pair(df,stale)

    def test_prompt_win_stat(self):
        df=select_pair(self.example_data(),'gemini-3.1-pro','gemini-3.8-flash')
        df['target_score']=np.where(df.label==1,.7,.3)
        s=per_prompt_stats(df)
        self.assertEqual(s['matched_prompts'],3)
        self.assertEqual(s['prompt_win_rate'],1.0)

if __name__=='__main__':
    unittest.main()
