"""Stable, frontend-facing projection of live analysis evidence.

M6 live jobs use a MOCK Harness judge: never convert a classifier candidate,
requested routing ID, or manually reviewed baseline into a new accepted model.
This module has NO DB, provider, or secret access.
"""
from __future__ import annotations

from typing import Any


def summarize_unvalidated_live_result(baseline: dict[str, Any] | None) -> dict[str, Any]:
    """Conservative view while the actual live judge/ML rejection is unvalidated."""
    prior = baseline['model_id'] if baseline is not None else None
    return {
        'schema_version': '1.0',
        'identification': {
            'status': 'needs_review',
            'accepted_model_id': None,
            'reason': 'live_judge_not_validated',
        },
        'comparison': {
            'status': 'insufficient_evidence' if prior else 'no_baseline',
            'previous_model_id': prior,
            'current_model_id': None,
            'identity_change': None,
            'family_change': None,
            'card_comparison': {'status': 'not_comparable', 'changes': []},
        },
        'model_card': {'status': 'unavailable', 'model_id': None, 'card': None},
        'baseline': dict(baseline) if baseline is not None else None,
        'evidence': {'target_provider': 'openai', 'judge': 'mock',
                     'identity_confirmed': False, 'baseline_auto_updated': False},
    }
