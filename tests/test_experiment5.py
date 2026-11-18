import unittest
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rich_features import RichStylometryTransformer,ALL_NAMES,GROUPS
from train_rich_features import make_model
from train_hierarchical import compose_four_scores
from experiment_common import evaluate_target,breakdowns,prompt_ranking


class NewExperimentsTests(unittest.TestCase):
    def test_rich_transformer_and_ablation(self):
        X=['Hi!','```python\ndef foo():\n    return 23\n```','Some writing. Another sentence!']
        base=RichStylometryTransformer().transform(X)
        self.assertEqual(base.shape,(3,len(ALL_NAMES)))
        self.assertTrue(np.isfinite(base).all())
        self.assertTrue(np.isfinite(RichStylometryTransformer(drop_groups=('code',)).transform(X)).all())
        self.assertEqual(RichStylometryTransformer(drop_groups=('code',)).transform(X).shape[1],
                         len(ALL_NAMES)-len(GROUPS['code']))
        self.assertEqual(len(set(ALL_NAMES)),len(ALL_NAMES))

    def test_hierarchical_scores_and_hard_routing(self):
        pg=np.array([.95,.05,.65]); ppro=np.array([.9,.1,.4]); pl31=np.array([.2,.8,.6])
        scores=compose_four_scores(pg,ppro,pl31)
        self.assertEqual(len(scores),4)
        self.assertTrue(np.allclose(sum(scores.values()),1.0))
        self.assertGreater(scores['gemini-3.1-pro'][0],scores['llama3.1-8b'][0])
        self.assertGreater(scores['llama3.1-8b'][1],scores['gemini-3.1-pro'][1])

    def test_evaluation_and_subgroups(self):
        df=pd.DataFrame([{
            'record_id':str(i),'prompt_id':str(i//2),'prompt_category':'qa',
            'persona_id':'P13','model_key':'gemini-3.1-pro' if i%2==0 else 'gemini-3.8-flash'
        } for i in range(8)])
        scores=np.array([.9,.1,.8,.2,.7,.3,.6,.4])
        metrics,preds,t=evaluate_target(df,scores,'gemini-3.1-pro','toy','within_family',.1)
        self.assertEqual(len(metrics),2)
        self.assertEqual(metrics[0]['roc_auc'],1.0)
        breakdown=breakdowns(pd.concat(preds,ignore_index=True))
        sibling=breakdown[(breakdown.group_by=='actual_model') & (breakdown.group=='gemini-3.8-flash')]
        self.assertTrue((sibling.false_acceptance_rate==0).all())
        rank=prompt_ranking(df,scores,'gemini-3.1-pro','toy','within_family')
        self.assertEqual(rank.target_ranked_higher.sum(),4)

    def test_hard_gate_unachievable_false_alarm_does_not_accept_everything(self):
        df=pd.DataFrame([{
            'record_id':str(i),'prompt_id':str(i),'prompt_category':'qa',
            'persona_id':'P13','model_key':'gemini-3.1-pro' if i<5 else 'llama3.1-8b'
        } for i in range(10)])
        scores=np.array([0,0,.7,.8,.9,0,0,0,0,0],dtype=float)
        metrics,preds,t=evaluate_target(df,scores,'gemini-3.1-pro','toy',
                                         'hierarchy_hard_route',.1)
        self.assertGreater(t,0)
        self.assertFalse(metrics[1]['false_alarm_constraint_met'])
        self.assertEqual(int(preds[1].loc[preds[1].label==0,'predicted_target'].sum()),0)

    def test_model_constructors_fit_small_data(self):
        texts=['This is sentence number '+str(i)+' about '+('Python coding' if i%2 else 'cats animals') for i in range(14)]
        labels=np.asarray([i%2 for i in range(14)])
        for name in ('rich_rf','rich_lr','word_lr','char_lr','hybrid_lr'):
            with self.subTest(name=name):
                pipe=make_model(name,42,'unused')
                pipe.fit(texts,labels)
                pred=pipe.predict_proba(texts)
                self.assertEqual(pred.shape,(14,2))

if __name__=='__main__':unittest.main()
