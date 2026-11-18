"""Version-pinned five-class Random Forest identifier (Stage 2C).

Uses the repo's original prepare_fingerprint_rf.make_features to preserve
all 52 predictors and their order, and loads the trusted sklearn pipeline
produced by tools/export_random_forest.py. Only original response + metadata
are used. The expected and true identities are NEVER features.

The 5-way forest is closed-set: default review_only returns a candidate but
will not mark it accepted or claim drift. Acceptance requires independent
calibration with unsupported model examples and a versioned policy.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

from ..config import Stage2MethodSelection
from ..registry import ArtifactManifest
from ..schemas import IdentificationInput, IdentificationResult, Observation, ProbeQuestion
from . import rf_features


class RFConfigurationError(ValueError):
    """Invalid or incomplete forest artifact/feature contract."""


ScoreFunction = Callable[[object], Mapping[str, float]]
FEATURE_ABI = 'fingerprint_rf_52_v1'


class RandomForestIdentifier:
    name = 'random_forest'

    def __init__(self, manifest: ArtifactManifest, *, predictor: ScoreFunction | None = None):
        if manifest.adapter != 'random_forest' or manifest.stage != 2:
            raise RFConfigurationError('Expected Stage 2 random_forest manifest')
        self.manifest = manifest
        self.artifact_id = manifest.artifact_id
        if manifest.options.get('feature_abi') != FEATURE_ABI:
            raise RFConfigurationError('Unsupported feature ABI; an adapter upgrade is required')
        path = manifest.directory / 'feature_manifest.json'
        if not path.is_file():
            raise RFConfigurationError('feature_manifest.json is missing')
        feature_spec = json.loads(path.read_text(encoding='utf-8'))
        self.columns = tuple(feature_spec.get('feature_columns', []))
        self.prompt_ids = tuple(feature_spec.get('prompt_ids', []))
        if len(self.columns) != 52 or len(set(self.columns)) != len(self.columns):
            raise RFConfigurationError('Expected 52 unique ordered predictor columns')
        if feature_spec.get('target') != 'model_key' or not self.prompt_ids:
            raise RFConfigurationError('Original RF target or prompt IDs are missing')
        required = (list(rf_features.TEXT_FEATURES)
                    + [rf_features.prompt_feature_name(x) for x in self.prompt_ids]
                    + ['prompt_char_count', 'prompt_word_count']
                    + list(rf_features.BACKEND_FEATURES))
        if list(self.columns) != required:
            raise RFConfigurationError('Feature order differs from original extractor')
        if set(manifest.supported_models) != set(manifest.options.get('label_order', [])):
            raise RFConfigurationError('Supported models and ordered labels disagree')
        self.labels = tuple(manifest.options['label_order'])
        policy = manifest.options.get('acceptance_policy', {'mode': 'review_only'})
        if not isinstance(policy, dict) or policy.get('mode') not in ('review_only', 'validated_threshold'):
            raise RFConfigurationError('Unknown Random Forest acceptance policy')
        self.threshold = None
        if policy['mode'] == 'validated_threshold':
            threshold = policy.get('threshold')
            if (isinstance(threshold, bool) or not isinstance(threshold, (float, int))
                    or not math.isfinite(threshold) or not 0 < threshold <= 1):
                raise RFConfigurationError('Invalid validated_threshold')
            if (not isinstance(policy.get('validation_id'), str) or not policy['validation_id'].strip()
                    or policy.get('includes_unknown_models') is not True):
                raise RFConfigurationError('Threshold requires held-out unknown-model validation')
            self.threshold = float(threshold)
        self.acceptance_policy = policy['mode']
        self._predictor = predictor
        self._loaded = predictor is not None

    def required_probes(self) -> Sequence[ProbeQuestion]:
        return ()

    def make_feature_frame(self, observation: Observation):
        """Return a one-row DataFrame in exactly the training column order."""
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError('Install requirements-random-forest.txt (pandas)') from exc
        # make_features() adds model_key because it was originally a training
        # helper. We drop it completely: neither true nor expected ID is input.
        row = {
            # The recorded RF numeric tables use LF-normalized text even
            # when the current processed CSV contains CRLF in response fields.
            # Normalize line endings before counting chars/punctuation.
            'response_text': observation.response_text.replace('\r\n', '\n').replace('\r', '\n'),
            'prompt': observation.prompt_text,
            'prompt_id': observation.prompt_id or '',
            'output_tokens': observation.output_tokens,
            'latency_ms': observation.latency_ms,
            'model_key': '__not_supplied_to_predictor__',
        }
        result = rf_features.make_features(row, list(self.prompt_ids), list(self.columns))
        result.pop('model_key')
        return pd.DataFrame([result], columns=list(self.columns))

    def _load_predictor(self) -> ScoreFunction:
        # Repeat the readiness check even when the adapter is called directly,
        # bypassing the Factory. joblib is a pickle format: only load artifacts
        # that the project itself trained and deliberately trusted.
        for entry in self.manifest.required_files:
            path = (self.manifest.directory / entry.relative_path).resolve()
            if not path.is_relative_to(self.manifest.directory.resolve()):
                raise RFConfigurationError('Artifact path escapes its version directory')
            if not path.is_file() or not entry.sha256:
                raise RFConfigurationError(f'Missing or unchecksummed RF file: {entry.relative_path}')
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != entry.sha256:
                    raise RFConfigurationError(f'RF checksum mismatch: {entry.relative_path}')
        artifact_code = (self.manifest.directory / 'feature_extractor.py').read_bytes()
        adapter_code = Path(rf_features.__file__).read_bytes()
        if artifact_code != adapter_code:
            raise RFConfigurationError('Installed feature extractor differs from the training-version source')
        try:
            import joblib
            import sklearn
        except ImportError as exc:
            raise RuntimeError('Install requirements-random-forest.txt') from exc
        trained_version = self.manifest.options.get('sklearn_version')
        if sklearn.__version__ != trained_version:
            raise RFConfigurationError(
                f'RF saved with scikit-learn {trained_version}, currently running {sklearn.__version__}')
        model = joblib.load(self.manifest.directory / 'classifier.joblib')
        # The training artifact used n_jobs=-1. For single-response service
        # inference, force one worker to avoid a large joblib parallelism
        # overhead; this changes no tree predictions.
        model.named_steps['randomforestclassifier'].n_jobs = 1
        if (not callable(getattr(model, 'predict_proba', None))
                or not hasattr(model, 'classes_')
                or list(model.classes_) != list(self.labels)):
            raise RFConfigurationError('Fitted estimator missing predict_proba or has different class order')
        feature_names = getattr(model, 'feature_names_in_', None)
        if feature_names is None or list(feature_names) != list(self.columns):
            raise RFConfigurationError('Estimator feature names/order differ from manifest')

        def run(frame):
            probs = model.predict_proba(frame)[0]
            return {label: float(score) for label, score in zip(self.labels, probs)}
        return run

    def identify(self, context: IdentificationInput) -> IdentificationResult:
        start = perf_counter()
        if not self._loaded:
            self._predictor = self._load_predictor()
            self._loaded = True
        frame = self.make_feature_frame(context.initial)
        scores = dict(self._predictor(frame))
        if set(scores) != set(self.labels):
            raise ValueError('RF scores do not match manifest class labels')
        values = list(scores.values())
        if (any(type(x) not in (float, int) or not math.isfinite(x) or not 0 <= x <= 1
                for x in values) or abs(sum(values) - 1.0) > 1e-3):
            raise ValueError('RF predict_proba must return finite normalized scores')
        candidate = max(self.labels, key=lambda k: scores[k])
        confidence = float(scores[candidate])
        accepted = self.threshold is not None and confidence >= self.threshold
        known_prompt = context.initial.prompt_id in self.prompt_ids
        missing_backend = (context.initial.output_tokens is None or context.initial.latency_ms is None)
        return IdentificationResult(
            method='random_forest', outcome='identified' if accepted else 'unknown',
            candidate_model_id=candidate, accepted_model_id=candidate if accepted else None,
            score=confidence, score_type='rf_predict_proba',
            handoff_requested=not accepted,
            model_scores={k: float(scores[k]) for k in self.labels},
            reason=('Candidate accepted under externally validated policy' if accepted else
                    'Closed-set RF candidate only; identity requires review'),
            duration_ms=(perf_counter() - start) * 1000,
            diagnostics={
                'artifact_id': self.artifact_id,
                'closed_set': True,
                'acceptance_policy': self.acceptance_policy,
                'acceptance_threshold': self.threshold,
                'feature_abi': FEATURE_ABI,
                'input': 'initial_response_and_prompt_metadata',
                'prompt_id_known': known_prompt,
                'output_tokens_missing': context.initial.output_tokens is None,
                'latency_ms_missing': context.initial.latency_ms is None,
                'distribution_shift_warning': (not known_prompt or missing_backend),
            })


def build_random_forest(manifest: ArtifactManifest,
                        selection: Stage2MethodSelection) -> RandomForestIdentifier:
    if selection.adapter != 'random_forest' or selection.artifact_id != manifest.artifact_id:
        raise RFConfigurationError('Random Forest selection does not match artifact')
    return RandomForestIdentifier(manifest)
