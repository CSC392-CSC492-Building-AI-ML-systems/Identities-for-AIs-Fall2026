"""Versioned inference-artifact registry (metadata only, no deserialization).

Paths must stay inside the project or the relevant version directory. A
registered artifact may not be ready; readiness is an independent check.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model_catalog import ModelCatalog

ARTIFACT_RE = re.compile(r'^[a-z][a-z0-9_-]*/[a-z][a-z0-9._-]*$')
ADAPTER_STAGE = {
    'logistic_regression': 1,
    'lora': 2,
    'harness': 2,
    'random_forest': 2,
}


class RegistryError(ValueError):
    pass


def _require_relative(path: str, parent: Path) -> Path:
    if (not isinstance(path, str) or not path or '\\' in path or
            Path(path).is_absolute() or ':' in path or
            any(x in ('.', '..') for x in Path(path).parts)):
        raise RegistryError(f'Unsafe or invalid relative path: {path!r}')
    root = parent.resolve()
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise RegistryError(f'Path escapes its artifact root: {path!r}')
    return resolved


def _json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f'Cannot load JSON {path}: {exc}') from exc
    if not isinstance(data, dict):
        raise RegistryError(f'Expected JSON object in {path}')
    return data


@dataclass(frozen=True)
class RequiredFile:
    relative_path: str
    sha256: str | None = None


@dataclass(frozen=True)
class ArtifactManifest:
    artifact_id: str
    adapter: str
    stage: int
    kind: str
    supported_models: tuple[str, ...]
    required_files: tuple[RequiredFile, ...]
    manifest_path: Path
    manifest_sha256: str
    options: dict[str, Any]
    provenance: dict[str, Any]

    @property
    def directory(self) -> Path:
        return self.manifest_path.parent

    def supports(self, model_id: str) -> bool:
        return model_id in self.supported_models


@dataclass(frozen=True)
class ReadinessReport:
    artifact_id: str
    ready: bool
    missing_files: tuple[str, ...]
    checksum_failures: tuple[str, ...]
    unchecksummed_files: tuple[str, ...]


class ArtifactRegistry:
    """Discovers version manifests; never loads .joblib, .pt, or other weights."""

    def __init__(self, root: str | Path, catalog: ModelCatalog):
        self.root = Path(root).resolve()
        self.catalog = catalog
        index = _json_file(self.root / 'models' / 'registry.json')
        if index.get('schema_version') != '1.0':
            raise RegistryError('Registry requires schema_version 1.0')
        entries = index.get('artifacts')
        if not isinstance(entries, dict) or not entries:
            raise RegistryError('Registry artifacts must be a nonempty object')
        self._paths: dict[str, Path] = {}
        for artifact_id, path in entries.items():
            if not isinstance(artifact_id, str) or not ARTIFACT_RE.fullmatch(artifact_id):
                raise RegistryError(f'Invalid artifact ID {artifact_id!r}')
            manifest_path = _require_relative(path, self.root)
            if manifest_path.suffix != '.json':
                raise RegistryError(f'{artifact_id}: manifest path must end in .json')
            self._paths[artifact_id] = manifest_path
        self._cache: dict[str, ArtifactManifest] = {}

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._paths))

    def get(self, artifact_id: str) -> ArtifactManifest:
        if artifact_id in self._cache:
            return self._cache[artifact_id]
        path = self._paths.get(artifact_id)
        if path is None:
            raise RegistryError(f'Unregistered artifact version: {artifact_id!r}')
        raw = _json_file(path)
        if raw.get('schema_version') != '1.0' or raw.get('artifact_id') != artifact_id:
            raise RegistryError(f'{artifact_id}: manifest ID or schema version mismatch')
        adapter = raw.get('adapter')
        stage = raw.get('stage')
        if adapter not in ADAPTER_STAGE or type(stage) is not int or stage != ADAPTER_STAGE[adapter]:
            raise RegistryError(f'{artifact_id}: unsupported adapter/stage: {adapter!r}/{stage!r}')
        kind = raw.get('kind')
        if not isinstance(kind, str) or not kind:
            raise RegistryError(f'{artifact_id}: kind must be nonempty')
        models = raw.get('supported_models')
        if not isinstance(models, list) or not models or any(not isinstance(m, str) for m in models):
            raise RegistryError(f'{artifact_id}: supported_models must be a nonempty list of strings')
        if len(set(models)) != len(models):
            raise RegistryError(f'{artifact_id}: duplicate supported models')
        for m in models:
            self.catalog.get(m)
        raw_files = raw.get('required_files')
        if not isinstance(raw_files, list) or not raw_files:
            raise RegistryError(f'{artifact_id}: required_files must be a nonempty list')
        files: list[RequiredFile] = []
        for item in raw_files:
            if not isinstance(item, dict):
                raise RegistryError(f'{artifact_id}: required_files items must be objects')
            rel = item.get('path')
            _require_relative(rel, path.parent)
            digest = item.get('sha256')
            if digest is not None and (not isinstance(digest, str) or
                                        not re.fullmatch(r'[0-9a-f]{64}', digest)):
                raise RegistryError(f'{artifact_id}: invalid sha256 for {rel}')
            files.append(RequiredFile(rel, digest))
        if len(set(f.relative_path for f in files)) != len(files):
            raise RegistryError(f'{artifact_id}: duplicate required files')
        options = raw.get('options', {})
        provenance = raw.get('provenance', {})
        if not isinstance(options, dict) or not isinstance(provenance, dict):
            raise RegistryError(f'{artifact_id}: options/provenance must be objects')
        result = ArtifactManifest(artifact_id, adapter, stage, kind, tuple(models),
                                  tuple(files), path, hashlib.sha256(path.read_bytes()).hexdigest(),
                                  options, provenance)
        self._cache[artifact_id] = result
        return result

    def readiness(self, artifact_id: str) -> ReadinessReport:
        manifest = self.get(artifact_id)
        missing, bad_digests, unchecked = [], [], []
        for item in manifest.required_files:
            file_path = _require_relative(item.relative_path, manifest.directory)
            if not file_path.is_file():
                missing.append(item.relative_path)
            elif item.sha256 is not None:
                with file_path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != item.sha256:
                    bad_digests.append(item.relative_path)
            else:
                unchecked.append(item.relative_path)
        # A file without a registered checksum is not yet a reproducible release.
        return ReadinessReport(artifact_id, not (missing or bad_digests or unchecked), tuple(missing),
                               tuple(bad_digests), tuple(unchecked))
