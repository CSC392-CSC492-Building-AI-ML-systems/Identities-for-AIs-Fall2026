import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fingerprinting.config import (ConfigurationError, check_config_readiness,
                                   load_pipeline_config)
from fingerprinting.model_catalog import CatalogError, ModelCatalog
from fingerprinting.registry import ArtifactRegistry, RegistryError

ROOT = Path(__file__).resolve().parent.parent


class ArtifactAndConfigTests(unittest.TestCase):
    def setUp(self):
        self.catalog = ModelCatalog.from_file(ROOT / 'catalog/models.json')
        self.registry = ArtifactRegistry(ROOT, self.catalog)

    def test_catalog_contains_collector_models(self):
        self.assertGreaterEqual(len(self.catalog.model_ids), 17)
        self.assertEqual(self.catalog.get('gemini-3.1-pro').family_id, 'gemini')
        self.assertEqual(self.catalog.get('gemini-3.8-flash').product_line, 'Gemini Flash')
        self.assertEqual(self.catalog.get('llama3.2-3b').developer, 'Meta')

    def test_model_identity_is_not_classifier_artifact_id(self):
        self.assertTrue(self.catalog.has('llama3.1-8b'))
        self.assertFalse(self.catalog.has('random_forest/v1'))

    def test_expected_family_consistency(self):
        self.catalog.validate_expected('gemini-3.1-pro', 'gemini')
        with self.assertRaises(CatalogError):
            self.catalog.validate_expected('gemini-3.1-pro', 'llama')
        with self.assertRaises(CatalogError):
            self.catalog.get('unregistered-model')

    def test_registry_contains_four_explicit_versions(self):
        self.assertEqual(set(self.registry.artifact_ids),
                         {'stage1_lr/v1', 'lora/v1', 'lora/v2', 'harness/v1', 'random_forest/v1'})

    def test_registry_has_correct_method_stage_and_support(self):
        lr = self.registry.get('stage1_lr/v1')
        self.assertEqual((lr.adapter, lr.stage), ('logistic_regression', 1))
        self.assertTrue(lr.supports('gemini-3.1-pro'))
        self.assertFalse(lr.supports('qwen3-8b'))
        self.assertEqual(self.registry.get('harness/v1').stage, 2)
        self.assertEqual(self.registry.get('lora/v1').adapter, 'lora')

    def test_unknown_classifier_version_is_rejected(self):
        with self.assertRaises(RegistryError):
            self.registry.get('lora/v99')

    def test_valid_production_configuration(self):
        cfg = load_pipeline_config(ROOT/'config/production.yaml', self.registry)
        self.assertEqual(cfg.stage1.approach, 'hierarchy_hard_route')
        self.assertEqual(cfg.stage2.mode, 'fallback')
        self.assertEqual([m.adapter for m in cfg.stage2.methods],
                         ['lora', 'harness', 'random_forest'])
        self.assertEqual(len(cfg.config_sha256), 64)
        self.assertEqual(cfg.snapshot()['stage2']['mode'], 'fallback')

    def test_independent_stage2_config_files(self):
        for adapter in ('lora', 'harness', 'random_forest'):
            cfg = load_pipeline_config(ROOT/f'config/experiments/{adapter}_only.yaml', self.registry)
            self.assertEqual(cfg.stage2.mode, 'single')
            self.assertEqual(cfg.stage2.methods[0].adapter, adapter)

    def test_run_all_configuration(self):
        cfg = load_pipeline_config(ROOT/'config/evaluation.yaml', self.registry)
        self.assertEqual(cfg.stage2.mode, 'run_all')
        self.assertEqual(len(cfg.stage2.methods), 3)

    def test_new_lora_ready_but_historical_v1_incomplete(self):
        cfg = load_pipeline_config(ROOT/'config/production.yaml', self.registry)
        report = check_config_readiness(cfg, self.registry)
        self.assertTrue(report['ready'])
        self.assertTrue(report['artifacts']['lora/v2']['ready'])
        self.assertTrue(report['artifacts']['random_forest/v1']['ready'])
        old = self.registry.readiness('lora/v1')
        self.assertFalse(old.ready)
        self.assertIn('adapter_model.safetensors',old.missing_files)

    def test_duplicate_yaml_mapping_key_rejected(self):
        text = (ROOT/'config/production.yaml').read_text()
        text = text.replace('  name: fingerprinting_default',
                            '  name: fingerprinting_default\n  name: duplicate')
        self.assert_config_rejected(text, 'Duplicate YAML key')

    def test_wrong_adapter_for_manifest_rejected(self):
        text = (ROOT/'config/production.yaml').read_text()
        text = text.replace('adapter: lora, artifact: lora/v2',
                            'adapter: harness, artifact: lora/v2')
        self.assert_config_rejected(text)

    def test_unknown_version_rejected_during_config_validation(self):
        text = (ROOT/'config/production.yaml').read_text().replace('lora/v2','lora/v99')
        self.assert_config_rejected(text, 'Unregistered artifact')

    def test_single_mode_rejects_multiple_methods(self):
        text = (ROOT/'config/production.yaml').read_text().replace('mode: fallback','mode: single')
        self.assert_config_rejected(text, 'requires exactly one')

    def test_duplicate_method_rejected(self):
        text = (ROOT/'config/production.yaml').read_text().replace(
            'adapter: harness, artifact: harness/v1', 'adapter: lora, artifact: lora/v2')
        self.assert_config_rejected(text, 'Duplicate Stage 2')

    def test_invalid_stage1_approach_rejected(self):
        text = (ROOT/'config/production.yaml').read_text().replace('hierarchy_hard_route','magic_algorithm')
        self.assert_config_rejected(text)

    def test_extra_config_keys_rejected(self):
        text = (ROOT/'config/production.yaml').read_text().replace('cards:', 'secret: ignored\ncards:')
        self.assert_config_rejected(text, 'unexpected keys')

    def test_yaml_unsafe_python_tag_rejected(self):
        text = (ROOT/'config/production.yaml').read_text().replace('name: fingerprinting_default',
                     'name: !!python/object/apply:os.system ["echo unsafe"]')
        self.assert_config_rejected(text, 'Invalid YAML')

    def assert_config_rejected(self, content, contains=None):
        with tempfile.TemporaryDirectory() as t:
            file = Path(t)/'pipeline.yaml'
            file.write_text(content)
            with self.assertRaises(ConfigurationError) as error:
                load_pipeline_config(file, self.registry)
            if contains:
                self.assertIn(contains, str(error.exception))

    def test_manifest_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'models').mkdir()
            (root/'models/registry.json').write_text(json.dumps({
                'schema_version':'1.0','artifacts': {'lora/v1': '../outside/manifest.json'}}))
            with self.assertRaises(RegistryError):
                ArtifactRegistry(root, self.catalog)

    def test_required_artifact_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'models/lora/v1'; folder.mkdir(parents=True)
            source = json.loads((ROOT/'models/lora/v1/manifest.json').read_text())
            source['required_files'][0]['path']='../../secrets.txt'
            (folder/'manifest.json').write_text(json.dumps(source))
            (root/'models/registry.json').write_text(json.dumps({'schema_version':'1.0',
                       'artifacts':{'lora/v1':'models/lora/v1/manifest.json'}}))
            with self.assertRaises(RegistryError):
                ArtifactRegistry(root, self.catalog).get('lora/v1')

    def test_unknown_model_id_in_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'models/lora/v1'; folder.mkdir(parents=True)
            source = json.loads((ROOT/'models/lora/v1/manifest.json').read_text())
            source['supported_models'].append('not-a-real-model')
            (folder/'manifest.json').write_text(json.dumps(source))
            (root/'models/registry.json').write_text(json.dumps({'schema_version':'1.0',
                       'artifacts':{'lora/v1':'models/lora/v1/manifest.json'}}))
            with self.assertRaises(CatalogError):
                ArtifactRegistry(root, self.catalog).get('lora/v1')

    def test_version_switch_changes_selection_not_existing_strategy_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); d=root/'models/lora/v3'; d.mkdir(parents=True)
            source=json.loads((ROOT/'models/lora/v1/manifest.json').read_text())
            source['artifact_id']='lora/v3'
            (d/'manifest.json').write_text(json.dumps(source))
            index=json.loads((ROOT/'models/registry.json').read_text())
            # Map all unchanged manifests to their real location with test-controlled symlinks/copies.
            import shutil
            for aid, name in index['artifacts'].items():
                origin=ROOT/name
                dest=root/name
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(origin, dest)
            index['artifacts']['lora/v3']='models/lora/v3/manifest.json'
            (root/'models/registry.json').write_text(json.dumps(index))
            fresh=ArtifactRegistry(root, self.catalog)
            cfg_old=load_pipeline_config(ROOT/'config/production.yaml', fresh)
            text=(ROOT/'config/production.yaml').read_text().replace('lora/v2','lora/v3')
            new_file=root/'new.yaml'; new_file.write_text(text)
            cfg_new=load_pipeline_config(new_file, fresh)
            self.assertEqual(cfg_old.stage2.methods[0].artifact_id, 'lora/v2')
            self.assertEqual(cfg_new.stage2.methods[0].artifact_id, 'lora/v3')
            self.assertNotEqual(cfg_old.config_sha256, cfg_new.config_sha256)

    def test_hash_based_readiness_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); d=root/'models/lora/v1'; d.mkdir(parents=True)
            filename=d/'adapter_config.json'; filename.write_bytes(b'known bytes')
            source=json.loads((ROOT/'models/lora/v1/manifest.json').read_text())
            source['required_files']=[{'path':'adapter_config.json',
                'sha256':hashlib.sha256(b'known bytes').hexdigest()}]
            (d/'manifest.json').write_text(json.dumps(source))
            (root/'models/registry.json').write_text(json.dumps({'schema_version':'1.0',
                'artifacts':{'lora/v1':'models/lora/v1/manifest.json'}}))
            registry=ArtifactRegistry(root,self.catalog)
            self.assertTrue(registry.readiness('lora/v1').ready)
            filename.write_bytes(b'changed bytes')
            r=registry.readiness('lora/v1')
            self.assertFalse(r.ready)
            self.assertEqual(r.checksum_failures, ('adapter_config.json',))

    def test_present_but_unchecksummed_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); d=root/'models/lora/v1'; d.mkdir(parents=True)
            (d/'adapter_config.json').write_text('ok')
            source=json.loads((ROOT/'models/lora/v1/manifest.json').read_text())
            source['required_files']=[{'path':'adapter_config.json','sha256':None}]
            (d/'manifest.json').write_text(json.dumps(source))
            (root/'models/registry.json').write_text(json.dumps({'schema_version':'1.0',
                'artifacts':{'lora/v1':'models/lora/v1/manifest.json'}}))
            r=ArtifactRegistry(root,self.catalog).readiness('lora/v1')
            self.assertFalse(r.ready)
            self.assertEqual(r.unchecksummed_files,('adapter_config.json',))


if __name__ == '__main__':
    unittest.main()
