"""Dependency-injected factory for constructing a configured FingerprintPipeline.

Configuration selects *which* strategy and artifact to use; constructor hooks
supply *how* to initialize that implementation. This module deliberately does
not import or load model weights, notebooks, pickles or remote API clients.

For production, leave require_ready=True (default) and register real builders.
For deterministic unit tests, explicit require_ready=False allows builders for
StubStage1/StubIdentifier to exercise config-driven construction with the
metadata-only manifests shipped in this repository.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .config import (ALLOWED_STAGE1_APPROACHES, ALLOWED_STAGE2_MODES,
                     STAGE2_ADAPTERS, PipelineConfig, Stage1Selection,
                     Stage2MethodSelection, check_config_readiness)
from .interfaces import CardResolver, Stage1Strategy, Stage2Identifier, Stage2Strategy
from .pipeline import FingerprintPipeline
from .registry import ArtifactManifest, ArtifactRegistry, RegistryError
from .strategies import FallbackStrategy, RunAllStrategy, SingleMethodStrategy

Stage1Builder = Callable[[ArtifactManifest, Stage1Selection], Stage1Strategy]
Stage2Builder = Callable[[ArtifactManifest, Stage2MethodSelection], Stage2Identifier]


class FactoryError(ValueError):
    """Invalid factory construction, missing adapter, or unavailable artifacts."""


@dataclass
class AdapterConstructors:
    """Explicit builder registration instead of importing dynamic dotted paths.

    Builder functions own adapter-specific initialization and can load/cache
    weights when they are implemented. No eval(), auto-import, or dynamic
    constructor strings appear in configuration or artifact manifests.
    """

    stage1: dict[str, Stage1Builder] = field(default_factory=dict)
    stage2: dict[str, Stage2Builder] = field(default_factory=dict)

    def register_stage1(self, adapter: str, builder: Stage1Builder) -> None:
        if not adapter or not callable(builder):
            raise FactoryError('Stage 1 requires a nonempty adapter name and callable builder')
        if adapter in self.stage1:
            raise FactoryError(f'Stage 1 constructor already registered: {adapter!r}')
        self.stage1[adapter] = builder

    def register_stage2(self, adapter: str, builder: Stage2Builder) -> None:
        if not adapter or not callable(builder):
            raise FactoryError('Stage 2 requires a nonempty adapter name and callable builder')
        if adapter in self.stage2:
            raise FactoryError(f'Stage 2 constructor already registered: {adapter!r}')
        self.stage2[adapter] = builder


def _verify_config_integrity(config: PipelineConfig) -> None:
    if not isinstance(config, PipelineConfig):
        raise FactoryError('Expected a validated PipelineConfig from load_pipeline_config()')
    payload = json.dumps(config.snapshot(), sort_keys=True, separators=(',', ':')).encode('utf-8')
    digest = hashlib.sha256(payload).hexdigest()
    if digest != config.config_sha256:
        raise FactoryError('PipelineConfig snapshot does not match config_sha256; reload config from YAML')
    if config.stage1.adapter != 'logistic_regression' or config.stage1.approach not in ALLOWED_STAGE1_APPROACHES:
        raise FactoryError('Unsupported Stage 1 adapter or approach')
    if config.stage2.mode not in ALLOWED_STAGE2_MODES:
        raise FactoryError(f'Invalid Stage 2 mode {config.stage2.mode!r}')
    methods = config.stage2.methods
    if not methods or (config.stage2.mode == 'single' and len(methods) != 1):
        raise FactoryError('Stage 2 must have methods; single mode requires exactly one')
    adapters = [m.adapter for m in methods]
    if any(a not in STAGE2_ADAPTERS for a in adapters) or len(set(adapters)) != len(adapters):
        raise FactoryError('Unknown or duplicate Stage 2 adapters')


def _verify_stage1(instance: Any, adapter: str) -> None:
    if not callable(getattr(instance, 'verify', None)):
        raise FactoryError(f'Stage 1 builder {adapter!r} did not return a Stage1Strategy (missing verify)')
    if not isinstance(getattr(instance, 'name', None), str) or not instance.name:
        raise FactoryError(f'Stage 1 builder {adapter!r} returned strategy without a name')


def _verify_stage2(instance: Any, adapter: str) -> None:
    if not callable(getattr(instance, 'identify', None)) or not callable(getattr(instance, 'required_probes', None)):
        raise FactoryError(f'Stage 2 builder {adapter!r} did not return a Stage2Identifier')
    if getattr(instance, 'name', None) != adapter:
        raise FactoryError(f'Stage 2 builder {adapter!r} returned method name {getattr(instance, "name", None)!r}')


class PipelineFactory:
    """Builds the runtime Context with configured, interchangeable strategies.

    require_ready=False MUST only be used with mock/test constructors. Real
    deployment construction uses the default require_ready=True to reject
    incomplete or unchecksummed artifact versions before instantiating any
    expensive classifier resources.
    """

    def __init__(self, registry: ArtifactRegistry, constructors: AdapterConstructors,
                 *, require_ready: bool = True, card_resolver: CardResolver | None = None):
        self.registry = registry
        self.constructors = constructors
        self.require_ready = require_ready
        self.card_resolver = card_resolver

    def build_stage1(self, config: PipelineConfig) -> Stage1Strategy:
        """Create only Stage 1 for independent tests, without loading Stage 2 weights.

        Stage 2 selections remain metadata-validated by load_pipeline_config,
        but their runtime artifacts and constructors are not required here.
        """
        _verify_config_integrity(config)
        if config.stage1.adapter not in self.constructors.stage1:
            raise FactoryError(f'No Stage 1 builder registered for {config.stage1.adapter!r}')
        selection = config.stage1
        try:
            manifest = self.registry.get(selection.artifact_id)
        except RegistryError as exc:
            raise FactoryError(str(exc)) from exc
        if manifest.adapter != selection.adapter or manifest.stage != 1:
            raise FactoryError('Stage 1 selection does not match artifact manifest')
        if selection.approach not in manifest.options.get('approaches', []):
            raise FactoryError('Unsupported Stage 1 approach for selected artifact')
        if hashlib.sha256(manifest.manifest_path.read_bytes()).hexdigest() != manifest.manifest_sha256:
            raise FactoryError('Stage 1 manifest changed after it was loaded')
        if self.require_ready:
            status = self.registry.readiness(selection.artifact_id)
            if not status.ready:
                raise FactoryError(f'Stage 1 artifact is not ready: {status}')
        try:
            stage1 = self.constructors.stage1[selection.adapter](manifest, selection)
        except Exception as exc:
            raise FactoryError(f'Failed to initialize Stage 1 {selection.artifact_id}: {exc}') from exc
        _verify_stage1(stage1, selection.adapter)
        return stage1

    def build_stage2(self, config: PipelineConfig) -> Stage2Strategy:
        """Build only selected Stage 2 methods for independent evaluation.

        Stage 1 does not need to load or be ready for this operation. Real
        inference still requires all *selected Stage 2* artifacts to be ready.
        """
        _verify_config_integrity(config)
        identifiers = []
        manifests = []
        for choice in config.stage2.methods:
            try:
                manifest = self.registry.get(choice.artifact_id)
            except RegistryError as exc:
                raise FactoryError(str(exc)) from exc
            if manifest.stage != 2 or manifest.adapter != choice.adapter:
                raise FactoryError(f'Invalid Stage 2 selection: {choice.artifact_id}')
            if hashlib.sha256(manifest.manifest_path.read_bytes()).hexdigest() != manifest.manifest_sha256:
                raise FactoryError(f'Stage 2 manifest changed after registry loading: {choice.artifact_id}')
            if choice.adapter not in self.constructors.stage2:
                raise FactoryError(f'No Stage 2 builder registered for {choice.adapter!r}')
            manifests.append((choice, manifest))
        if self.require_ready:
            for choice, _ in manifests:
                readiness = self.registry.readiness(choice.artifact_id)
                if not readiness.ready:
                    raise FactoryError(f'Stage 2 artifact is not ready: {choice.artifact_id}: {readiness}')
        for choice, manifest in manifests:
            try:
                instance = self.constructors.stage2[choice.adapter](manifest, choice)
            except Exception as exc:
                raise FactoryError(f'Failed to initialize Stage 2 {choice.artifact_id}: {exc}') from exc
            _verify_stage2(instance, choice.adapter)
            identifiers.append(instance)
        if config.stage2.mode == 'single':
            return SingleMethodStrategy(identifiers[0])
        if config.stage2.mode == 'fallback':
            return FallbackStrategy(identifiers)
        return RunAllStrategy(identifiers)

    def build(self, config: PipelineConfig) -> FingerprintPipeline:
        """Build Stage 2 by default; construct Stage 1 only when enabled.

        The optional Stage 1 may be loaded later with pipeline.run(...,
        use_stage1=True). Disabled Stage 1 never blocks construction or
        requires its weights to be present.
        """
        _verify_config_integrity(config)
        if config.cards_enabled and self.card_resolver is None:
            raise FactoryError('cards.enabled=true requires an injected CardResolver')
        selected = ([config.stage1.artifact_id] if config.stage1.enabled else []) + [
            x.artifact_id for x in config.stage2.methods]
        if config.stage1.enabled and config.stage1.adapter not in self.constructors.stage1:
            raise FactoryError(f'No Stage 1 builder registered for {config.stage1.adapter!r}')
        for choice in config.stage2.methods:
            if choice.adapter not in self.constructors.stage2:
                raise FactoryError(f'No Stage 2 builder registered for {choice.adapter!r}')
        if self.require_ready:
            for artifact_id in selected:
                readiness = self.registry.readiness(artifact_id)
                if not readiness.ready:
                    raise FactoryError('Selected artifact bundles are not ready: '
                                       f'{artifact_id}: {readiness}')

        # When active, Stage 1 is built first to preserve the previous
        # construction order; when inactive it remains an on-demand dependency.
        stage1 = self.build_stage1(config) if config.stage1.enabled else None
        stage2 = self.build_stage2(config)
        ids = {'stage1': config.stage1.artifact_id, **{
            choice.adapter: choice.artifact_id for choice in config.stage2.methods}}
        hashes = {artifact_id: self.registry.get(artifact_id).manifest_sha256
                  for artifact_id in ids.values()}
        return FingerprintPipeline(
            stage1, stage2,
            stage1_enabled=config.stage1.enabled,
            stage1_loader=lambda: self.build_stage1(config),
            cards=self.card_resolver if config.cards_enabled else None,
            config_sha256=config.config_sha256,
            artifact_ids=ids,
            manifest_sha256=hashes,
        )
