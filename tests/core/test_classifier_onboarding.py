"""Offline candidate onboarding regression tests. Never deserialize a submitted pickle."""
from __future__ import annotations
import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fingerprinting.onboarding.artifacts import (OnboardingError, candidate_config,
    register, validate, template, digest)
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.config import load_pipeline_config

ROOT=(Path(__file__).resolve().parents[2] / 'system')


class ClassifierOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'system'; self.root.mkdir()
        shutil.copytree(ROOT/'catalog',self.root/'catalog'); shutil.copytree(ROOT/'config',self.root/'config')
        (self.root/'models').mkdir(); shutil.copyfile(ROOT/'models/registry.json',self.root/'models/registry.json')
        self.index=self.root/'models/registry.json'
        for name in json.loads(self.index.read_text())['artifacts'].values():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
        self.bundle=Path(self.tmp.name)/'submission';self.bundle.mkdir()
        rf=ROOT/'models/random_forest/v1'
        for f in ('feature_extractor.py','feature_manifest.json'):
            shutil.copyfile(rf/f,self.bundle/f)
        # Deliberately not a pickle: metadata onboarding must never deserialize it.
        (self.bundle/'classifier.joblib').write_bytes(b'NOT AN EXECUTABLE PICKLE')
        self.manifest=json.loads((rf/'manifest.json').read_text());self.manifest['artifact_id']='random_forest/test-candidate'
        for x in self.manifest['required_files']:x['sha256']=None
        self.dataset=self.root/'datasets/fixture/manifest.json';self.dataset.parent.mkdir(parents=True)
        self.dataset.write_text(json.dumps({'dataset_id':'fixture'}))
        self.manifest['provenance']={'source':'trusted test fixture','training_dataset_id':'fixture',
            'dataset_manifest_sha256':digest(self.dataset),'split_id':'fixture-split-v1','training_code_revision':'fixture-commit',
            'runtime_dependencies':{'python':'3.11','scikit-learn':'1.8.0'}}
        self.save()
    def save(self):
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))
    def reg(self):
        return ArtifactRegistry(self.root,ModelCatalog.from_file(self.root/'catalog/models.json'))
    def test_validate_does_not_mutate_or_deserialize(self):
        before=self.index.read_bytes();source=(self.bundle/'manifest.json').read_bytes()
        with patch('joblib.load',side_effect=AssertionError('no pickle execution')):
            report=validate(self.root,self.bundle)
        self.assertEqual(report['status'],'metadata_checked');self.assertFalse(report['runtime_validated']); self.assertFalse(report['activated'])
        self.assertEqual(self.index.read_bytes(),before); self.assertEqual((self.bundle/'manifest.json').read_bytes(),source)
        self.assertFalse((self.root/'models/random_forest/test-candidate').exists())
    def test_register_then_candidate_config_and_preserve_original(self):
        before=(self.root/'config/production.yaml').read_bytes(); old=(self.root/'models/random_forest/v1/manifest.json').read_bytes()
        with patch('joblib.load',side_effect=AssertionError('no pickle execution')):
            report=register(self.root,self.bundle,trust_bundle=True)
        self.assertTrue(self.reg().readiness('random_forest/test-candidate').ready);self.assertEqual(report['status'],'registered_candidate')
        out=self.root/'config/experiments/rf_candidate.yaml'; candidate_config(self.root,'random_forest/test-candidate',out,single=True)
        cfg=load_pipeline_config(out,self.reg());self.assertEqual(cfg.stage2.methods[0].artifact_id,'random_forest/test-candidate'); self.assertFalse(cfg.stage1.enabled)
        self.assertEqual((self.root/'config/production.yaml').read_bytes(),before);self.assertEqual((self.root/'models/random_forest/v1/manifest.json').read_bytes(),old)
        with self.assertRaises(OnboardingError): register(self.root,self.bundle,trust_bundle=True)
    def test_explicit_trust_required(self):
        with self.assertRaisesRegex(OnboardingError,'trust-bundle'):register(self.root,self.bundle)
    def test_declared_checksum_mismatch(self):
        self.manifest['required_files'][0]['sha256']='0'*64;self.save()
        with self.assertRaisesRegex(OnboardingError,'Checksum mismatch'):validate(self.root,self.bundle)
    def test_unlisted_payload_rejected(self):
        (self.bundle/'unlisted.txt').write_text('x')
        with self.assertRaisesRegex(OnboardingError,'inventory mismatch'):validate(self.root,self.bundle)
    def test_missing_payload_rejected(self):
        (self.bundle/'classifier.joblib').unlink()
        with self.assertRaisesRegex(OnboardingError,'inventory mismatch'):validate(self.root,self.bundle)
    def test_traversal_rejected(self):
        self.manifest['required_files'][0]['path']='../classifier.joblib';self.save()
        with self.assertRaisesRegex(OnboardingError,'Unsafe'):validate(self.root,self.bundle)
    def test_unknown_catalog_label(self):
        self.manifest['supported_models'][0]='not-a-catalog-id';self.save()
        with self.assertRaisesRegex(ValueError,'Unknown canonical'):validate(self.root,self.bundle)
    def test_rf_feature_change_requires_adapter_upgrade(self):
        with (self.bundle/'feature_extractor.py').open('ab') as f:f.write(b'\n# changed\n')
        with self.assertRaisesRegex(OnboardingError,'adapter upgrade'):validate(self.root,self.bundle)
    def test_unapproved_acceptance_rejected(self):
        self.manifest['options']['acceptance_policy']={'mode':'validated_threshold','threshold':.9};self.save()
        with self.assertRaisesRegex(OnboardingError,'review_only'):validate(self.root,self.bundle)
    def test_wrong_local_dataset_hash(self):
        self.manifest['provenance']['dataset_manifest_sha256']='0'*64;self.save()
        with self.assertRaisesRegex(OnboardingError,'Local dataset'):validate(self.root,self.bundle)
    def test_missing_provenance(self):
        del self.manifest['provenance']['split_id'];self.save()
        with self.assertRaisesRegex(OnboardingError,'split_id'):validate(self.root,self.bundle)
    def test_prefix_mismatch(self):
        self.manifest['artifact_id']='lora/v9';self.save()
        with self.assertRaisesRegex(OnboardingError,'prefix'):validate(self.root,self.bundle)
    def test_template_no_overwrite(self):
        dest=Path(self.tmp.name)/'template.json';template(self.root,'random_forest/v1','random_forest/v3',dest)
        m=json.loads(dest.read_text());self.assertEqual(m['provenance']['split_id'],'TODO');self.assertTrue(all(x['sha256'] is None for x in m['required_files']))
        with self.assertRaises(FileExistsError):template(self.root,'random_forest/v1','random_forest/v3',dest)
    def test_concurrent_writer_lock(self):
        (self.root/'models/.onboarding.lock').write_text('busy')
        with self.assertRaisesRegex(OnboardingError,'locked'):register(self.root,self.bundle,trust_bundle=True)
    def test_failed_register_leaves_registry_unchanged(self):
        before=self.index.read_bytes()
        with patch('fingerprinting.onboarding.artifacts.os.replace',side_effect=OSError('write failure')):
            with self.assertRaises(OSError):register(self.root,self.bundle,trust_bundle=True)
        self.assertEqual(self.index.read_bytes(),before);self.assertFalse((self.root/'models/random_forest/test-candidate').exists());self.assertFalse((self.root/'models/.onboarding.lock').exists())
    def test_stage1_expansion_refused(self):
        self.manifest['artifact_id']='stage1_lr/v2';self.manifest['adapter']='logistic_regression';self.manifest['stage']=1;self.save()
        with self.assertRaisesRegex(OnboardingError,'Stage 1 adapter upgrade'):validate(self.root,self.bundle)
    def clone_fixture(self, old, new):
        # These are copies of existing artifacts, never real new model releases.
        path=Path(self.tmp.name)/new.replace('/','_')
        shutil.copytree(ROOT/'models'/old,path)
        raw=json.loads((path/'manifest.json').read_text());raw['artifact_id']=new
        raw['provenance']=self.manifest['provenance'].copy()
        if old.startswith('lora'):
            # Synthetic commit only for offline structural validation.
            raw['options']['base_model_revision']='a'*40
        (path/'manifest.json').write_text(json.dumps(raw));return path,raw
    def test_real_artifact_contracts_without_execution(self):
        for old,new in [('stage1_lr/v1','stage1_lr/v2'),('lora/v2','lora/v3'),('harness/v1','harness/test-candidate')]:
            with self.subTest(artifact=old):
                p,raw=self.clone_fixture(old,new)
                with patch('joblib.load',side_effect=AssertionError('no pickle execution')), patch('subprocess.run',side_effect=AssertionError('no source execution')):
                    self.assertEqual(validate(self.root,p)['status'],'metadata_checked')
    def test_lora_rejects_unpinned_base_revision(self):
        p,raw=self.clone_fixture('lora/v2','lora/v3');raw['options']['base_model_revision']='main'
        (p/'manifest.json').write_text(json.dumps(raw))
        with self.assertRaisesRegex(OnboardingError,'pinned'):validate(self.root,p)
    def test_lora_rejects_wrong_head_shape(self):
        p,raw=self.clone_fixture('lora/v2','lora/v3');raw['options']['classifier_head_shape']=[6,896]
        (p/'manifest.json').write_text(json.dumps(raw))
        with self.assertRaisesRegex(OnboardingError,'head shape'):validate(self.root,p)
    def test_harness_rejects_heldout_rows(self):
        p,raw=self.clone_fixture('harness/v1','harness/test-candidate')
        ref=next(x for x in raw['required_files'] if x['path'].endswith('fingerprint_v0.jsonl'))
        path=p/ref['path']; row=json.loads(path.read_text().splitlines()[0]);row['sample_index']=2
        with path.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        ref['sha256']=None;(p/'manifest.json').write_text(json.dumps(raw))
        with self.assertRaisesRegex(OnboardingError,'Non-reference'):validate(self.root,p)
    def test_production_config_not_overwritten(self):
        register(self.root,self.bundle,trust_bundle=True); before=(self.root/'config/production.yaml').read_bytes()
        with self.assertRaises(FileExistsError):candidate_config(self.root,'random_forest/test-candidate',self.root/'config/production.yaml')
        self.assertEqual((self.root/'config/production.yaml').read_bytes(),before)

if __name__=='__main__':unittest.main()
