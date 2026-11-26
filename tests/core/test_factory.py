"""Factory integration tests using deterministic stubs, NEVER real model weights."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fingerprinting.config import load_pipeline_config
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.eval_suite import with_stage1_enabled
from fingerprinting.factory import AdapterConstructors, FactoryError, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import (EvaluationCase, FingerprintRequest, IdentificationResult,
                                    Observation, Stage1Result)
from fingerprinting.testing import StubIdentifier, StubStage1

ROOT = (Path(__file__).resolve().parents[2] / 'system')


def request(request_id='fixture-1'):
    return FingerprintRequest(
        request_id, Observation('Explain Fibonacci numbers', 'The sequence starts 0, 1...', 'q-1'),
        'llama3.1-8b', 'llama', domain='risk')


def make_builders(log=None, stage1_verdict='mismatch', stage2_outcomes=None):
    log = log if log is not None else []
    stage2_outcomes = stage2_outcomes or {'lora': 'unknown', 'harness': 'identified', 'random_forest': 'identified'}
    constructors = AdapterConstructors()

    def build_stage1(manifest, selection):
        log.append(('stage1', manifest.artifact_id, selection.approach))
        verified = stage1_verdict == 'verified'
        return StubStage1(f'{selection.approach}:{manifest.artifact_id}', Stage1Result(
            stage1_verdict, family_match=True, model_match=verified, approach=selection.approach))

    def build_stage2(manifest, selection):
        log.append(('stage2', manifest.artifact_id, selection.adapter))
        outcome = stage2_outcomes[selection.adapter]
        target = 'llama3.2-3b'
        return StubIdentifier(selection.adapter, IdentificationResult(
            selection.adapter, outcome, candidate_model_id=target,
            accepted_model_id=target if outcome == 'identified' else None,
            diagnostics={'mock': True, 'artifact_id': manifest.artifact_id}))

    constructors.register_stage1('logistic_regression', build_stage1)
    for name in ('lora', 'harness', 'random_forest'):
        constructors.register_stage2(name, build_stage2)
    return constructors


class PipelineFactoryTests(unittest.TestCase):
    def setUp(self):
        self.catalog = ModelCatalog.from_file(ROOT/'catalog/models.json')
        self.registry = ArtifactRegistry(ROOT, self.catalog)
        self.config = with_stage1_enabled(load_pipeline_config(ROOT/'config/production.yaml', self.registry), True)

    def create(self, config=None, builders=None, require_ready=False, **kwargs):
        return PipelineFactory(self.registry, builders or make_builders(),
                               require_ready=require_ready, **kwargs).build(config or self.config)

    def test_factory_builds_ordered_fallback_from_yaml(self):
        log = []
        pipeline = self.create(builders=make_builders(log))
        self.assertEqual([m.name for m in pipeline.stage2.identifiers],
                         ['lora', 'harness', 'random_forest'])
        self.assertEqual(log, [('stage1', 'stage1_lr/v1', 'hierarchy_hard_route'),
                               ('stage2', 'lora/v2', 'lora'), ('stage2', 'harness/v1', 'harness'),
                               ('stage2', 'random_forest/v1', 'random_forest')])
        result = pipeline.run(request())
        self.assertEqual(result.final.resolved_by, 'harness')
        self.assertEqual([r.method for r in result.stage2_attempts], ['lora', 'harness'])
        self.assertEqual(result.final.status, 'drift_detected')

    def test_provenance_includes_config_and_each_manifest(self):
        result = self.create().run(request()).to_dict()
        self.assertEqual(result['config_sha256'], self.config.config_sha256)
        self.assertEqual(result['artifact_ids'], {'stage1': 'stage1_lr/v1',
                         'lora': 'lora/v2', 'harness': 'harness/v1', 'random_forest': 'random_forest/v1'})
        self.assertEqual(result['manifest_sha256'], {name: self.registry.get(name).manifest_sha256
                         for name in result['artifact_ids'].values()})
        json.dumps(result)

    def test_stage1_verified_short_circuits_after_factory_build(self):
        p = self.create(builders=make_builders(stage1_verdict='verified'))
        result = p.run(request())
        self.assertEqual(result.final.resolved_by, 'stage1')
        self.assertFalse(result.stage2_attempts)
        self.assertEqual(result.config_sha256, self.config.config_sha256)

    def test_run_all_configuration_compares_all_identifiers(self):
        cfg = with_stage1_enabled(load_pipeline_config(ROOT/'config/evaluation.yaml', self.registry), True)
        result = self.create(cfg).run(request())
        self.assertEqual([r.method for r in result.stage2_attempts],
                         ['lora', 'harness', 'random_forest'])
        self.assertEqual(result.final.resolved_by, 'harness')
        self.assertEqual(result.stage2_strategy, 'compare_all_lora_harness_random_forest')
        self.assertEqual(result.stage1.approach, 'hierarchy_soft')

    def test_configurable_single_methods(self):
        for method in ('lora', 'harness', 'random_forest'):
            cfg = load_pipeline_config(ROOT/f'config/experiments/{method}_only.yaml', self.registry)
            p = self.create(cfg)
            self.assertEqual([m.name for m in p.stage2.identifiers], [method])
            result = p.run(request())
            self.assertEqual([r.method for r in result.stage2_attempts], [method])

    def test_default_factory_builds_with_checksums_after_v2_install(self):
        log = []
        self.create(builders=make_builders(log), require_ready=True)
        self.assertEqual(len(log), 4)
        self.assertIn(('stage2', 'lora/v2', 'lora'), log)

    def test_missing_stage1_builder_fails_preconstruction(self):
        constructors = AdapterConstructors()
        for name in ('lora', 'harness', 'random_forest'):
            constructors.register_stage2(name, lambda manifest, choice: None)
        with self.assertRaisesRegex(FactoryError, 'No Stage 1 builder'):
            self.create(builders=constructors)

    def test_missing_stage2_builder_fails_preconstruction(self):
        log = []
        builders = make_builders(log)
        del builders.stage2['harness']
        with self.assertRaisesRegex(FactoryError, "No Stage 2 builder"):
            self.create(builders=builders)
        self.assertEqual(log, [])

    def test_builder_stage1_contract_validation(self):
        constructors = make_builders()
        constructors.stage1['logistic_regression'] = lambda m, s: object()
        with self.assertRaisesRegex(FactoryError, 'missing verify'):
            self.create(builders=constructors)

    def test_builder_stage2_contract_validation(self):
        constructors = make_builders()
        constructors.stage2['harness'] = lambda m, s: object()
        with self.assertRaisesRegex(FactoryError, 'did not return a Stage2Identifier'):
            self.create(builders=constructors)

    def test_builder_stage2_rejects_wrong_name(self):
        constructors = make_builders()
        constructors.stage2['harness'] = lambda m, s: StubIdentifier('lora', IdentificationResult('lora', 'unknown'))
        with self.assertRaisesRegex(FactoryError, 'returned method name'):
            self.create(builders=constructors)

    def test_builder_initialization_error_is_labeled(self):
        constructors = make_builders()
        def fail(m, c):
            raise RuntimeError('Intentional simulated initialization error')
        constructors.stage2['harness'] = fail
        with self.assertRaisesRegex(FactoryError, 'Failed to initialize Stage 2 harness/v1'):
            self.create(builders=constructors)

    def test_duplicate_builder_registration_rejected(self):
        constructors = make_builders()
        with self.assertRaisesRegex(FactoryError, 'already registered'):
            constructors.register_stage2('lora', lambda m, s: None)

    def test_mutated_validated_config_rejected(self):
        forged = replace(self.config, name='altered-after-validation')
        with self.assertRaisesRegex(FactoryError, 'does not match config_sha256'):
            self.create(forged)

    def test_config_with_valid_digest_but_wrong_adapter_rejected(self):
        s1 = replace(self.config.stage1, adapter='lora')
        forged = replace(self.config, stage1=s1)
        digest = hashlib.sha256(json.dumps(forged.snapshot(), sort_keys=True,
                                        separators=(',', ':')).encode()).hexdigest()
        forged = replace(forged, config_sha256=digest)
        with self.assertRaisesRegex(FactoryError, 'Unsupported Stage 1'):
            self.create(forged)

    def test_cards_enabled_requires_injected_resolver(self):
        forged = replace(self.config, cards_enabled=True)
        digest = hashlib.sha256(json.dumps(forged.snapshot(), sort_keys=True,
                                        separators=(',', ':')).encode()).hexdigest()
        forged = replace(forged, config_sha256=digest)
        with self.assertRaisesRegex(FactoryError, 'CardResolver'):
            self.create(forged)
        class Card:
            def resolve(self, model_id, domain=None):
                return {'model_id': model_id, 'domain': domain}
        p = self.create(forged, card_resolver=Card())
        self.assertEqual(p.run(request()).domain_card,
                         {'model_id': 'llama3.2-3b', 'domain': 'risk'})

    def test_same_strategy_supports_independent_evaluation(self):
        cfg = load_pipeline_config(ROOT/'config/experiments/lora_only.yaml', self.registry)
        pipeline = self.create(cfg)
        case = EvaluationCase('case', request(), 'llama3.2-3b', 'llama', 'mock', 'test')
        report = EvaluationRunner.stage2([case], pipeline.stage2)
        self.assertEqual(report.metrics['n_cases'], 1)
        self.assertEqual(report.metrics['unresolved'], 1)
        e2e = EvaluationRunner.e2e([case], pipeline)
        self.assertEqual(e2e.metrics['n_cases'], 1)

    def test_manifest_changed_after_registry_load_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for artifact_id in self.registry.artifact_ids:
                rel = f'models/{artifact_id}/manifest.json'
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((ROOT / rel).read_bytes())
            (root/'models/registry.json').write_bytes((ROOT/'models/registry.json').read_bytes())
            registry = ArtifactRegistry(root, self.catalog)
            cfg = load_pipeline_config(ROOT/'config/production.yaml', registry)
            manifest = registry.get('lora/v2')
            manifest.manifest_path.write_text(manifest.manifest_path.read_text() + '\n')
            with self.assertRaisesRegex(FactoryError, '[Mm]anifest changed after'):
                PipelineFactory(registry, make_builders(), require_ready=False).build(cfg)

    def test_production_readiness_passes_with_complete_checksums(self):
        # Test-only dummy bytes. This verifies the readiness gate, NOT that
        # such files are valid serialized ML models or safe to deserialize.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifacts = {}
            for artifact_id in ('stage1_lr/v1', 'lora/v2'):
                relative = f'models/{artifact_id}/manifest.json'
                source = json.loads((ROOT / relative).read_text())
                folder = root / 'models' / artifact_id
                folder.mkdir(parents=True, exist_ok=True)
                for req in source['required_files']:
                    target = folder / req['path']
                    target.parent.mkdir(parents=True, exist_ok=True)
                    payload = f'dummy fixture for {artifact_id}/{req["path"]}'.encode()
                    target.write_bytes(payload)
                    req['sha256'] = hashlib.sha256(payload).hexdigest()
                (folder / 'manifest.json').write_text(json.dumps(source))
                artifacts[artifact_id] = relative
            (root/'models/registry.json').write_text(json.dumps({
                'schema_version': '1.0', 'artifacts': artifacts}))
            registry = ArtifactRegistry(root, self.catalog)
            cfg_text = (ROOT/'config/experiments/lora_only.yaml').read_text()
            cfg_path = root/'config.yaml'; cfg_path.write_text(cfg_text)
            cfg = load_pipeline_config(cfg_path, registry)
            pipeline = PipelineFactory(registry, make_builders(), require_ready=True).build(cfg)
            self.assertEqual(pipeline.run(request()).artifact_ids['lora'], 'lora/v2')

    def test_version_switch_without_code_change(self):
        """Register a second manifest and change only the YAML artifact selection."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'models/lora/v3').mkdir(parents=True)
            (root/'models/stage1_lr/v1').mkdir(parents=True)
            (root/'models/harness/v1').mkdir(parents=True)
            (root/'models/random_forest/v1').mkdir(parents=True)
            idx = json.loads((ROOT/'models/registry.json').read_text())
            idx['artifacts']['lora/v3'] = 'models/lora/v3/manifest.json'
            (root/'models/registry.json').write_text(json.dumps(idx))
            for artifact_id, relative in idx['artifacts'].items():
                if artifact_id == 'lora/v3':
                    data = json.loads((ROOT/'models/lora/v1/manifest.json').read_text())
                    data['artifact_id'] = 'lora/v3'
                    (root/relative).write_text(json.dumps(data))
                elif artifact_id != 'lora/v1':
                    (root/relative).parent.mkdir(parents=True, exist_ok=True)
                    (root/relative).write_bytes((ROOT/relative).read_bytes())
                else:
                    dest=root/relative; dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_bytes((ROOT/relative).read_bytes())
            registry = ArtifactRegistry(root, self.catalog)
            content = (ROOT/'config/production.yaml').read_text().replace('lora/v2', 'lora/v3')
            conf = root/'production.yaml'
            conf.write_text(content)
            cfg = load_pipeline_config(conf, registry)
            seen=[]
            pipeline = PipelineFactory(registry, make_builders(seen), require_ready=False).build(cfg)
            self.assertIn(('stage2','lora/v3','lora'), seen)
            result = pipeline.run(request())
            self.assertEqual(result.artifact_ids['lora'], 'lora/v3')
            self.assertEqual(result.final.resolved_by, 'harness')
            self.assertNotEqual(result.config_sha256, self.config.config_sha256)


if __name__ == '__main__':
    unittest.main()
