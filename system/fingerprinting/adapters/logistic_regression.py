"""Trusted, versioned Stage 1 classifier adapter.

Implements Stage1Strategy without importing the original experiment package.
Scores and saved thresholds follow Experiment 6's predict_hierarchical.py;
Stage 1's *verdict* additionally enforces the project requirement that both
family routing and the within-family model label agree with expectations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from ..config import Stage1Selection
from ..registry import ArtifactManifest
from ..schemas import FingerprintRequest, Stage1Result

FAMILIES = {
    'gemini': ('gemini-3.1-pro', 'gemini-3.8-flash'),
    'llama': ('llama3.1-8b', 'llama3.2-3b'),
}
MODEL_TO_FAMILY = {model: family for family, models in FAMILIES.items() for model in models}
ALLOWED_APPROACHES = frozenset(('hierarchy_hard_route', 'hierarchy_soft', 'ovr_direct'))


def _positive_score(estimator: Any, response: str) -> float:
    """Original positive-class extraction, independent of classes_ order."""
    classes = list(estimator.classes_)
    if 1 not in classes:
        raise ValueError(f'Expected binary positive class 1, found {classes}')
    return float(estimator.predict_proba([response])[0, classes.index(1)])


@dataclass(frozen=True)
class _Threshold:
    target: str
    approach: str
    value: float


class LogisticRegressionVerifier:
    """Score single-response Gemini/Llama fingerprints using existing saved LR pipelines.

    Eagerly loads and reuses 7 trusted joblib pipelines; never retrains.
    The Python-facing interface is independent of the artifact's version.
    Do not construct this class with untrusted .joblib files.
    """

    def __init__(self, manifest: ArtifactManifest, approach: str):
        if manifest.adapter != 'logistic_regression' or manifest.stage != 1:
            raise ValueError('Expected a Stage 1 logistic_regression artifact manifest')
        if approach not in ALLOWED_APPROACHES or approach not in manifest.options.get('approaches', []):
            raise ValueError(f'Unsupported approach: {approach}')
        if set(manifest.supported_models) != set(MODEL_TO_FAMILY):
            raise ValueError('This adapter requires the four-model Gemini/Llama v1 class set')
        if manifest.options.get('decision_policy') != 'strict_two_check':
            raise ValueError('Unexpected Stage 1 decision policy; add a version-specific adapter')

        import joblib  # heavy imports deferred until an actual real adapter is constructed

        self.approach = approach
        self.artifact_id = manifest.artifact_id
        self.name = f'logistic_regression:{approach}:{manifest.artifact_id}'
        root = manifest.directory
        files = {entry.relative_path for entry in manifest.required_files}

        def load_one(filename: str):
            if filename not in files:
                raise ValueError(f'Unregistered classifier file: {filename}')
            model = joblib.load(root / filename)  # only for trusted, checksum-verified artifacts
            if not callable(getattr(model, 'predict_proba', None)):
                raise TypeError(f'{filename} lacks predict_proba')
            if set(getattr(model, 'classes_', [])) != {0, 1}:
                raise ValueError(f'{filename} must have binary classes [0,1]')
            return model

        self.family = load_one('family_gemini_vs_llama.joblib')
        self.conditional = {
            family: load_one(f'{family}_conditional_{models[0]}.joblib')
            for family, models in FAMILIES.items()
        }
        self.direct = {
            model_id: load_one(f'ovr_{model_id}.joblib')
            for model_id in MODEL_TO_FAMILY
        } if approach == 'ovr_direct' else {}

        self.thresholds: dict[str, _Threshold] = {}
        for model_id in MODEL_TO_FAMILY:
            filename = f'{approach}_{model_id}_threshold.json'
            if filename not in files:
                raise ValueError(f'Unregistered threshold file: {filename}')
            t = json.loads((root / filename).read_text(encoding='utf-8'))
            if t.get('target') != model_id or t.get('approach') != approach or t.get('algorithm') != 'baseline_lr':
                raise ValueError(f'Incompatible threshold metadata for {model_id}')
            value = float(t['validation_threshold'])
            if not (0.0 < value <= 1.0):
                raise ValueError(f'Invalid validation threshold in {filename}: {value}')
            self.thresholds[model_id] = _Threshold(model_id, approach, value)

    def verify(self, request: FingerprintRequest) -> Stage1Result:
        start = perf_counter()
        target = request.expected_model_id
        expected_family = request.expected_family_id
        if target not in MODEL_TO_FAMILY:
            raise ValueError(f'Model {target!r} is not supported by {self.artifact_id}')
        if MODEL_TO_FAMILY[target] != expected_family:
            raise ValueError(f'Expected family {expected_family!r} does not match catalog family for {target!r}')

        response = request.initial.response_text
        pg = _positive_score(self.family, response)
        within = {family: _positive_score(classifier, response)
                  for family, classifier in self.conditional.items()}
        scores_all = {
            'gemini-3.1-pro': pg * within['gemini'],
            'gemini-3.8-flash': pg * (1.0 - within['gemini']),
            'llama3.1-8b': (1.0 - pg) * within['llama'],
            'llama3.2-3b': (1.0 - pg) * (1.0 - within['llama']),
        }
        route = 'gemini' if pg >= 0.5 else 'llama'
        family_match = route == expected_family
        first, second = FAMILIES[route]
        selected_model = first if within[route] >= 0.5 else second
        target_cond = within[expected_family]
        if target == FAMILIES[expected_family][1]:
            target_cond = 1.0 - target_cond

        if self.approach == 'hierarchy_soft':
            raw_score = scores_all[target]
        elif self.approach == 'hierarchy_hard_route':
            raw_score = target_cond if family_match else 0.0
        else:
            raw_score = _positive_score(self.direct[target], response)

        threshold = self.thresholds[target].value
        raw_accept = raw_score >= threshold
        # The original experiment was a binary consistency test. Our production
        # pipeline is explicitly family -> *model identity* verification, so
        # acceptance requires the conditional model identity too.
        model_match = bool(raw_accept and selected_model == target) if family_match else None
        verified = family_match and model_match is True
        if not family_match:
            reason = 'Family prediction differs from expected family; model verification skipped'
        elif selected_model != target:
            reason = 'Within-family predicted model differs from expected model'
        elif not raw_accept:
            reason = 'Original target-model score fell below saved validation threshold'
        else:
            reason = 'Family and within-family model match; saved target threshold accepted'
        diagnostics = {
            'family_score_gemini': pg,
            'within_family_score_gemini_pro': within['gemini'],
            'within_family_score_llama3_1': within['llama'],
            'within_family_target_score': target_cond,
            'binary_target_score': raw_score,
            # A raw target-positive decision may differ from the stricter two-check verdict.
            'original_predicted_target': float(raw_accept),
        }
        diagnostics.update({f'soft_score:{key}': float(value) for key, value in scores_all.items()})
        return Stage1Result(
            verdict='verified' if verified else 'mismatch',
            predicted_family_id=route,
            predicted_model_id=selected_model if family_match else None,
            family_match=family_match,
            model_match=model_match,
            approach=self.approach,
            scores=diagnostics,
            thresholds={'target_validation_threshold': threshold,
                        'family_routing_threshold': 0.5,
                        'within_family_model_threshold': 0.5},
            reason=reason,
            duration_ms=(perf_counter() - start) * 1000.0,
        )


def build_logistic_regression(manifest: ArtifactManifest,
                              selection: Stage1Selection) -> LogisticRegressionVerifier:
    """Constructor registered by PipelineFactory; no version-dependent imports."""
    return LogisticRegressionVerifier(manifest, selection.approach)
