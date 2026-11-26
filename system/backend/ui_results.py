"""Stable, frontend-facing projection of live analysis evidence.

Legacy jobs use a mock judge; Stage 2 review jobs also never convert a classifier candidate,
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


def summarize_stage2_result(report, baseline, catalog, judge):
    """Allowlist structured candidate evidence; discard arbitrary judge/error text."""
    import math
    view = summarize_unvalidated_live_result(baseline)
    view['identification']['reason'] = ('methods_failed' if report.fingerprint.final.status == 'error'
                                         else 'acceptance_not_validated')
    view['evidence']['judge'] = judge
    attempts = {a.method: a for a in report.fingerprint.stage2_attempts}
    rows = []
    score_types = {'max_softmax', 'fit_score', 'rf_panel_predict_proba', 'rf_predict_proba'}
    for method in ('lora', 'harness', 'random_forest'):
        a = attempts.get(method)
        artifact = report.fingerprint.artifact_ids.get(method)
        row = {'method': method, 'artifact_id': artifact, 'status': 'not_configured',
               'candidate_model_id': None, 'score': None, 'score_type': None, 'probe_ids_used': []}
        if a is not None:
            row['status'] = 'error' if a.outcome == 'error' else 'abstained'
            row['probe_ids_used'] = [x for x in a.probe_ids_used if x in report.target_queries]
            if method == 'harness' and judge == 'mock' and a.outcome != 'error':
                row['status'] = 'mock_judge'
            elif a.outcome != 'error':
                if a.candidate_model_id is not None and catalog.has(a.candidate_model_id):
                    row['status'] = 'candidate'
                    row['candidate_model_id'] = a.candidate_model_id
                    if (a.score_type in score_types and isinstance(a.score, (int, float))
                            and not isinstance(a.score, bool) and math.isfinite(a.score) and 0 <= a.score <= 1):
                        row['score'], row['score_type'] = a.score, a.score_type
        elif artifact is not None:
            row['status'] = 'error'
        rows.append(row)
    ids = [r['candidate_model_id'] for r in rows if r['status'] == 'candidate']
    view['method_candidates'] = rows
    view['candidate_agreement'] = ('none' if not ids else 'single_candidate' if len(ids) == 1
                                  else 'agree' if len(set(ids)) == 1 else 'disagree')
    return view
