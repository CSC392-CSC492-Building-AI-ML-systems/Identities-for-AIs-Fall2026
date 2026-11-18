"""Validated YAML pipeline selection (not the trained-model loader or pipeline factory).

Selection depends on version manifests, but never imports model libraries or loads
weights. Invalid configurations fail before the pipeline can be constructed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .registry import ArtifactRegistry, RegistryError


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Stage1Selection:
    adapter: str
    artifact_id: str
    approach: str
    enabled: bool = False


@dataclass(frozen=True)
class Stage2MethodSelection:
    adapter: str
    artifact_id: str


@dataclass(frozen=True)
class Stage2Selection:
    mode: str
    methods: tuple[Stage2MethodSelection, ...]


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    stage1: Stage1Selection
    stage2: Stage2Selection
    cards_enabled: bool
    config_sha256: str
    source_path: Path

    def snapshot(self) -> dict[str, Any]:
        return {
            'schema_version': '1.0',
            'pipeline': {'name': self.name},
            'stage1': {'enabled': self.stage1.enabled, 'adapter': self.stage1.adapter,
                       'artifact': self.stage1.artifact_id, 'approach': self.stage1.approach},
            'stage2': {'mode': self.stage2.mode, 'methods': [
                {'adapter': m.adapter, 'artifact': m.artifact_id} for m in self.stage2.methods]},
            'cards': {'enabled': self.cards_enabled}}


ALLOWED_STAGE1_APPROACHES = frozenset({'hierarchy_hard_route', 'hierarchy_soft', 'ovr_direct'})
ALLOWED_STAGE2_MODES = frozenset({'single', 'fallback', 'run_all'})
STAGE2_ADAPTERS = frozenset({'lora', 'harness', 'random_forest'})


def _mapping(value: Any, name: str, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f'{name} must be an object')
    missing, unexpected = required - set(value), set(value) - allowed
    if missing:
        raise ConfigurationError(f'{name}: missing keys: {sorted(missing)}')
    if unexpected:
        raise ConfigurationError(f'{name}: unexpected keys: {sorted(unexpected)}')
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f'{name} must be a nonempty string')
    return value


def _load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigurationError('PyYAML is required for YAML configuration; install requirements.txt') from exc

    class UniqueSafeLoader(yaml.SafeLoader):
        pass

    def unique_mapping(loader, node):
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise ConfigurationError(f'YAML mapping keys must be strings: {key!r}')
            if key in mapping:
                raise ConfigurationError(f'Duplicate YAML key: {key!r}')
            mapping[key] = loader.construct_object(value_node, deep=True)
        return mapping

    UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
    try:
        return yaml.load(path.read_text(encoding='utf-8'), Loader=UniqueSafeLoader)
    except OSError as exc:
        raise ConfigurationError(f'Cannot read config {path}: {exc}') from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(f'Invalid YAML in {path}: {exc}') from exc


def load_pipeline_config(path: str | Path, registry: ArtifactRegistry) -> PipelineConfig:
    """Validate adapter/artifact consistency and return a version-pinned selection.

    This function performs metadata validation only; call registry.readiness() to
    check whether the required files are actually staged.
    """
    src = Path(path).resolve()
    raw = _mapping(_load_yaml(src), 'config',
                   {'schema_version', 'pipeline', 'stage1', 'stage2', 'cards'},
                   {'schema_version', 'pipeline', 'stage1', 'stage2'})
    if raw['schema_version'] != '1.0':
        raise ConfigurationError('Configuration requires schema_version 1.0')
    header = _mapping(raw['pipeline'], 'pipeline', {'name'}, {'name'})
    name = _string(header['name'], 'pipeline.name')
    stage1 = _mapping(raw['stage1'], 'stage1', {'enabled', 'adapter', 'artifact', 'approach'},
                      {'adapter', 'artifact', 'approach'})
    enabled = stage1.get('enabled', False)
    if type(enabled) is not bool:
        raise ConfigurationError('stage1.enabled must be a boolean')
    a1 = _string(stage1['adapter'], 'stage1.adapter')
    artifact1 = _string(stage1['artifact'], 'stage1.artifact')
    approach = _string(stage1['approach'], 'stage1.approach')
    if a1 != 'logistic_regression':
        raise ConfigurationError(f'Unsupported Stage 1 adapter {a1!r}')
    if approach not in ALLOWED_STAGE1_APPROACHES:
        raise ConfigurationError(f'Unsupported Stage 1 approach {approach!r}')
    try:
        manifest1 = registry.get(artifact1)
    except RegistryError as exc:
        raise ConfigurationError(str(exc)) from exc
    if manifest1.stage != 1 or manifest1.adapter != a1:
        raise ConfigurationError(f'Stage 1 artifact {artifact1!r} does not match adapter {a1!r}')
    supported_approaches = manifest1.options.get('approaches', [])
    if approach not in supported_approaches:
        raise ConfigurationError(f'{artifact1!r} does not declare support for {approach!r}')

    stage2 = _mapping(raw['stage2'], 'stage2', {'mode', 'methods'}, {'mode', 'methods'})
    mode = _string(stage2['mode'], 'stage2.mode')
    if mode not in ALLOWED_STAGE2_MODES:
        raise ConfigurationError(f'Unsupported Stage 2 mode {mode!r}')
    methods_raw = stage2['methods']
    if not isinstance(methods_raw, list) or not methods_raw:
        raise ConfigurationError('stage2.methods must be a nonempty list')
    if mode == 'single' and len(methods_raw) != 1:
        raise ConfigurationError('stage2.mode=single requires exactly one method')
    methods = []
    used = set()
    for i, item in enumerate(methods_raw):
        obj = _mapping(item, f'stage2.methods[{i}]', {'adapter', 'artifact'}, {'adapter', 'artifact'})
        adapter = _string(obj['adapter'], f'stage2.methods[{i}].adapter')
        art_id = _string(obj['artifact'], f'stage2.methods[{i}].artifact')
        if adapter not in STAGE2_ADAPTERS:
            raise ConfigurationError(f'Unknown Stage 2 adapter {adapter!r}')
        if adapter in used:
            raise ConfigurationError(f'Duplicate Stage 2 adapter {adapter!r}')
        used.add(adapter)
        try:
            manifest = registry.get(art_id)
        except RegistryError as exc:
            raise ConfigurationError(str(exc)) from exc
        if manifest.stage != 2 or manifest.adapter != adapter:
            raise ConfigurationError(f'Stage 2 artifact {art_id!r} does not match adapter {adapter!r}')
        methods.append(Stage2MethodSelection(adapter, art_id))

    cards = _mapping(raw.get('cards', {'enabled': False}), 'cards', {'enabled'}, {'enabled'})
    if type(cards['enabled']) is not bool:
        raise ConfigurationError('cards.enabled must be a boolean')
    selection = {
        'schema_version': '1.0', 'pipeline': {'name': name},
        'stage1': {'enabled': enabled, 'adapter': a1, 'artifact': artifact1, 'approach': approach},
        'stage2': {'mode': mode, 'methods': [
            {'adapter': m.adapter, 'artifact': m.artifact_id} for m in methods]},
        'cards': {'enabled': cards['enabled']}}
    digest = hashlib.sha256(json.dumps(selection, sort_keys=True, separators=(',', ':'))
                            .encode('utf-8')).hexdigest()
    return PipelineConfig(name, Stage1Selection(a1, artifact1, approach, enabled),
                          Stage2Selection(mode, tuple(methods)), cards['enabled'], digest, src)


def check_config_readiness(config: PipelineConfig, registry: ArtifactRegistry,
                           *, include_stage1: bool | None = None) -> dict[str, Any]:
    """Only active methods need to be ready. Stage 1 is optional by default."""
    active_stage1 = config.stage1.enabled if include_stage1 is None else include_stage1
    ids = ((config.stage1.artifact_id,) if active_stage1 else ()) + tuple(
        m.artifact_id for m in config.stage2.methods)
    rows = {k: registry.readiness(k) for k in ids}
    return {'ready': all(v.ready for v in rows.values()),
            'artifacts': {k: {
                'ready': v.ready, 'missing_files': list(v.missing_files),
                'checksum_failures': list(v.checksum_failures),
                'unchecksummed_files': list(v.unchecksummed_files)}
                for k, v in rows.items()}}
