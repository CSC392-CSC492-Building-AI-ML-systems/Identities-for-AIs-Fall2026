"""Canonical IDs for target LLMs. Separate from fingerprint classifier artifacts.

The catalog records identity metadata only: it does not imply support by any
classifier, expose evaluation labels, or contact model providers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class ModelIdentity:
    model_id: str
    family_id: str
    developer: str
    display_name: str
    product_line: str | None = None
    provider: str | None = None
    provider_model_id: str | None = None


class ModelCatalog:
    def __init__(self, entries: dict[str, ModelIdentity]):
        if not entries:
            raise CatalogError("Model catalog cannot be empty")
        self._entries = dict(entries)

    @classmethod
    def from_file(cls, path: str | Path) -> 'ModelCatalog':
        src = Path(path)
        try:
            document = json.loads(src.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"Cannot read model catalog {src}: {exc}") from exc
        if not isinstance(document, dict) or document.get('schema_version') != '1.0':
            raise CatalogError('Model catalog requires schema_version 1.0')
        raw = document.get('models')
        if not isinstance(raw, dict) or not raw:
            raise CatalogError('model catalog models must be a nonempty object')
        records: dict[str, ModelIdentity] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(value, dict):
                raise CatalogError(f'Invalid model entry: {key!r}')
            for field in ('family_id', 'developer', 'display_name'):
                if not isinstance(value.get(field), str) or not value[field].strip():
                    raise CatalogError(f'{key}: missing or invalid {field}')
            for optional in ('product_line', 'provider', 'provider_model_id'):
                if optional in value and value[optional] is not None and not isinstance(value[optional], str):
                    raise CatalogError(f'{key}: {optional} must be a string or null')
            records[key] = ModelIdentity(model_id=key, **{
                f: value.get(f) for f in ('family_id', 'developer', 'display_name',
                                           'product_line', 'provider', 'provider_model_id')})
        return cls(records)

    def get(self, model_id: str) -> ModelIdentity:
        try:
            return self._entries[model_id]
        except KeyError as exc:
            raise CatalogError(f'Unknown canonical model ID: {model_id!r}') from exc

    def has(self, model_id: str) -> bool:
        return model_id in self._entries

    def validate_expected(self, model_id: str, family_id: str) -> None:
        record = self.get(model_id)
        if record.family_id != family_id:
            raise CatalogError(
                f'{model_id!r} belongs to family {record.family_id!r}, not {family_id!r}')

    @property
    def model_ids(self) -> frozenset[str]:
        return frozenset(self._entries)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return {k: asdict(v) for k, v in self._entries.items()}
