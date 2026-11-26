"""Release workflow regressions; real trusted RF artifacts, no external calls."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fingerprinting import release as r
from fingerprinting.onboarding import artifacts as a

ROOT=(Path(__file__).resolve().parents[2] / 'system')


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.root=Path(cls.tmp.name)/'system';cls.root.mkdir()
        # Real data and artifacts in a private copy: never mutate the repository.
        for name in ('catalog','config','models','datasets','fingerprinting'):
            shutil.copytree(ROOT/name,cls.root/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        cls.evidence=Path(cls.tmp.name)/'evidence.json'
        cls.result=r.evaluate(cls.root,'random_forest/v2',cls.evidence,baseline='random_forest/v1',trust_artifacts=True)
        cls.base=cls.root/'config/experiments/random_forest_only.yaml'
        cls.note='Explicit local review; exploratory results only, not verified identification.'

    def altered(self,name,modify):
        value=copy.deepcopy(self.result);modify(value);path=Path(self.tmp.name)/(name+'.json');a.write_new(path,a.json_text(value));return path

    def publish(self,evidence,name,**kw):
        return r.publish(self.root,evidence,self.base,name,review_note=self.note,acknowledge_exploratory=True,**kw)

    def test_real_paired_validation(self):
        q=self.result
        self.assertEqual(q['candidate']['metrics']['cases'],51)
        self.assertEqual(q['candidate']['metrics']['correct'],49)
        self.assertEqual(q['baseline']['metrics']['cases'],51)
        self.assertEqual(q['shared_label_comparison']['candidate']['cases'],15)
        self.assertEqual(len(q['coverage']['baseline_missing_models']),12)
        self.assertEqual(q['target_api_calls'],0)
        self.assertFalse(q['independent_holdout_certified'])
        self.assertEqual([x['case_id'] for x in q['candidate']['rows']],[x['case_id'] for x in q['baseline']['rows']])
        self.assertEqual(q['candidate']['metrics']['accepted'],0)

    def test_missing_predictions_are_errors_for_accuracy(self):
        cat=a.existing(self.root).catalog
        row={'actual_model':'gemma3-4b','candidate_model':None,'accepted_model':None,'outcome':'error','duration_ms':None,'additional_probes':0}
        m=r.summarize([row],cat)
        self.assertEqual(m['accuracy'],0);self.assertEqual(m['candidate_coverage'],0);self.assertEqual(m['errors'],1)
        self.assertIn(r.MISSING,m['confusion_labels'])

    def test_publish_and_rollback_without_activation(self):
        original=a.digest(self.base);out=self.publish(self.evidence,'test-release')
        self.assertFalse(out['activated']);self.assertEqual(a.digest(self.base),original)
        dest=Path(out['config_path']);cfg,_=r._profile(self.root,dest)
        self.assertEqual(cfg.stage2.methods[0].artifact_id,'random_forest/v2')
        self.assertEqual(out['evaluation_sha256'],a.digest(dest.parent/'evaluation.json'))
        with self.assertRaisesRegex(ValueError,'already exists'):self.publish(self.evidence,'test-release')
        rb=r.rollback(self.root,'test-release','test-rollback',review_note=self.note)
        cfg,_=r._profile(self.root,Path(rb['config_path']));self.assertEqual(cfg.stage2.methods[0].artifact_id,'random_forest/v1')
        self.assertEqual(a.digest(self.base),original)
        self.assertTrue({'test-release','test-rollback'}<={x['release_id'] for x in r.history(self.root)})

    def test_acknowledgement_required(self):
        with self.assertRaisesRegex(ValueError,'Explicit exploratory review'):r.publish(self.root,self.evidence,self.base,'no-approval',review_note=self.note)

    def test_mock_and_partial_evidence_blocked(self):
        for name,field,value in [('mock','mock_only',True),('partial','complete_partition',False)]:
            path=self.altered(name,lambda x:x.update({field:value}))
            with self.assertRaisesRegex(ValueError,'complete, non-mock'):self.publish(path,name)

    def test_stale_manifest_blocked(self):
        path=self.altered('stale',lambda x:x['candidate'].update(manifest_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'Candidate manifest changed'):self.publish(path,'stale')

    def test_reordered_cohort_blocked(self):
        path=self.altered('bad-cohort',lambda x:x['candidate']['rows'].reverse())
        with self.assertRaisesRegex(ValueError,'complete pinned cohort'):self.publish(path,'bad-cohort')

    def test_legacy_lora_unconfirmed_and_stage1_blocked(self):
        for artifact in ('lora/v2','stage1_lr/v1'):
            with self.assertRaises(ValueError):r.evaluate(self.root,artifact,Path(self.tmp.name)/'invalid.json',trust_artifacts=True)

    def test_no_trust_no_execution(self):
        with self.assertRaisesRegex(ValueError,'trusted team'):r.evaluate(self.root,'random_forest/v2',Path(self.tmp.name)/'not-run.json')

    def test_eval_run_skips_harness_and_reused(self):
        rid='a'*32;directory=self.root/'.local/training_runs'/rid;directory.mkdir(parents=True)
        a.write_new(directory/'result.json',a.json_text({'run_id':rid,'methods':{'harness':{'status':'registered_candidate','artifact_id':'harness/v2'},'random_forest':{'status':'skipped_unchanged'}}}))
        with patch.object(r,'evaluate',side_effect=AssertionError('No execution expected')):
            out=r.evaluate_run(self.root,rid,self.base,trust_artifacts=True)
        self.assertEqual(out['methods']['harness']['status'],'needs_explicit_judge_review');self.assertEqual(out['methods']['random_forest']['status'],'skipped')

    def test_actual_training_to_automatic_evaluation(self):
        from fingerprinting.training import orchestrator as o
        config=a.read_json(self.root/'config/training/rf_panel_candidate.json')
        spec=config['methods']['random_forest'];spec['artifact_id']='random_forest/test-release-auto';spec['parameters'].update(probe_budget=1,n_estimators=5)
        trained=o.run(self.root,config,o.available_trainers(),approve_dataset=True,register_candidates=True)
        self.assertEqual(trained['status'],'completed',trained)
        result=r.evaluate_run(self.root,trained['run_id'],self.base,trust_artifacts=True)
        auto=result['methods']['random_forest'];self.assertEqual(auto['status'],'evaluated',auto)
        self.assertEqual(auto['candidate_metrics']['cases'],51)
        self.assertEqual(auto['candidate_metrics']['errors'],0)
        self.assertFalse(result['auto_activated'])

    def test_path_safety(self):
        with self.assertRaisesRegex(ValueError,'Invalid release ID'):r._release_dir(self.root,'../outside')


if __name__=='__main__':unittest.main()
