"""Read the team's *authoritative* sibling cards/ library, without copying card data.

No card content is generated for unsupported models. A source card's `confirmed`
field means an exact model card rather than a family aggregate; it is NOT proof
that a fingerprint prediction was confirmed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


class CardsUnavailable(Exception):
    pass


class RepositoryCards:
    DOMAINS = ('compliance', 'governance', 'evaluation', 'risk')

    def __init__(self, repository_root: Path | str | None = None):
        self.repository_root = (Path(repository_root) if repository_root else
                                Path(__file__).resolve().parents[2]).resolve()
        self.card_source = self.repository_root / 'cards' / 'cardlib.py'
        self._module = None

    def _library(self):
        if self._module is not None:
            return self._module
        if not self.card_source.is_file():
            raise CardsUnavailable('Sibling cards/cardlib.py not installed')
        spec = importlib.util.spec_from_file_location('fingerprinting_repo_cardlib', self.card_source)
        if spec is None or spec.loader is None:
            raise CardsUnavailable('Unable to load card library')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not callable(getattr(module, 'build_card', None)):
            raise CardsUnavailable('cardlib.build_card is missing')
        self._module = module
        return module

    def get(self, model_id: str) -> dict[str, Any] | None:
        try:
            result = self._library().build_card(model_id)
        except KeyError:
            return None
        if not isinstance(result, dict) or result.get('model_key') != model_id:
            raise CardsUnavailable('Card library returned an incompatible exact-model card')
        return result


def field_changes(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    """Diff stable domain/field IDs, not top-level documents or retrieval dates.

    Treat a changed source citation separately from a changed substantive value.
    Do not claim a comparison when either card is absent.
    """
    if before is None or after is None:
        return {'status': 'card_unavailable', 'changes': []}
    def index(card):
        return {(domain['domain'], field['id']): field
                for domain in card.get('domains', []) for field in domain.get('fields', [])}
    old, new = index(before), index(after)
    differences = []
    for domain, field_id in sorted(old.keys() | new.keys()):
        a, b = old.get((domain, field_id)), new.get((domain, field_id))
        va, vb = a.get('value') if a else None, b.get('value') if b else None
        sa, sb = a.get('source') if a else None, b.get('source') if b else None
        ma, mb = bool(a.get('missing')) if a else True, bool(b.get('missing')) if b else True
        if (va, sa, ma) != (vb, sb, mb):
            differences.append({'domain': domain, 'field_id': field_id,
                'name': (b or a).get('name'), 'before_value': va, 'after_value': vb,
                'before_missing': ma, 'after_missing': mb,
                'value_changed': va != vb or ma != mb, 'source_changed': sa != sb,
                'before_source': sa, 'after_source': sb})
    return {'status': 'compared', 'changes': differences}
