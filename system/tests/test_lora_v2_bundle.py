"""Test actual supplied LoRA bytes and immutable manifest hashing without network."""
import hashlib
import json
import unittest
from pathlib import Path
from safetensors import safe_open
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.adapters.lora import LoRAIdentifier
from fingerprinting.config import load_pipeline_config
from fingerprinting.schemas import IdentificationInput, Observation

ROOT=Path(__file__).resolve().parents[1]


class TestLoRAV2Bundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=ArtifactRegistry(ROOT,ModelCatalog.from_file(ROOT/'catalog/models.json'))

    def test_original_v1_preserved_and_v2_registered(self):
        self.assertIn('lora/v1',self.reg.artifact_ids)
        self.assertIn('lora/v2',self.reg.artifact_ids)
        v2=self.reg.get('lora/v2')
        self.assertEqual(v2.options['base_model'],'Qwen/Qwen2.5-0.5B')
        self.assertEqual(v2.options['lora_rank'],16)
        self.assertEqual(v2.options['lora_alpha'],32)
        self.assertEqual(v2.options['label_order_status'],'provisional_unconfirmed')
        self.assertEqual(LoRAIdentifier(v2,predictor=lambda _: (.2,)*5).acceptance_policy,'review_only')

    def test_real_files_checksums_and_five_class_head(self):
        manifest=self.reg.get('lora/v2')
        self.assertTrue(self.reg.readiness('lora/v2').ready)
        for item in manifest.required_files:
            with (manifest.directory / item.relative_path).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),item.sha256)
        cfg=json.loads((manifest.directory/'adapter_config.json').read_text())
        self.assertEqual(cfg['base_model_name_or_path'],manifest.options['base_model'])
        self.assertEqual(cfg['task_type'],'SEQ_CLS')
        with safe_open(manifest.directory/'adapter_model.safetensors',framework='pt',device='cpu') as f:
            self.assertEqual(list(f.get_slice('base_model.model.score.weight').get_shape()),[5,896])

    def test_unconfirmed_mapping_does_not_assign_a_model_name(self):
        v2=self.reg.get('lora/v2')
        obj=LoRAIdentifier(v2, predictor=lambda _: (.1,.6,.1,.1,.1))
        result=obj.identify(IdentificationInput(Observation('Q','A')))
        self.assertIsNone(result.candidate_model_id)
        self.assertIsNone(result.accepted_model_id)
        self.assertFalse(result.model_scores)
        self.assertEqual(result.diagnostics['raw_class_probabilities'],[.1,.6,.1,.1,.1])
        self.assertEqual(result.outcome,'unknown')

    def test_production_selects_v2(self):
        cfg=load_pipeline_config(ROOT/'config/production.yaml',self.reg)
        self.assertEqual(cfg.stage2.methods[0].artifact_id,'lora/v2')
        self.assertFalse(cfg.stage1.enabled)

if __name__=='__main__':unittest.main()
