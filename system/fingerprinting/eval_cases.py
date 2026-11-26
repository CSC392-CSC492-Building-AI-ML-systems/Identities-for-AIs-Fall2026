"""Offline evaluation-case I/O and reproducible conversions from existing data.

The true identity is ONLY placed in EvaluationCase, never into FingerprintRequest.
One row describes one expected/actual deployment scenario, not an independent
training example. In particular, multiple expected identities may reuse one answer.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from .model_catalog import ModelCatalog
from .schemas import EvaluationCase, FingerprintRequest, Observation


class EvaluationDataError(ValueError):
    pass


def _observation(raw: dict, *, probe_id: str | None = None) -> Observation:
    if not isinstance(raw, dict):
        raise EvaluationDataError('Observation must be an object')
    try:
        return Observation(
            prompt_text=raw['prompt_text'], response_text=raw['response_text'],
            prompt_id=raw.get('prompt_id') or probe_id,
            output_tokens=raw.get('output_tokens'), latency_ms=raw.get('latency_ms'),
            completed_blank=raw.get('completed_blank',False))
    except (KeyError, TypeError, ValueError) as exc:
        raise EvaluationDataError(f'Invalid observation: {exc}') from exc


def parse_case(raw: dict, catalog: ModelCatalog) -> EvaluationCase:
    """Fail closed for unknown labels, wrong families and malformed replay probes."""
    if not isinstance(raw, dict):
        raise EvaluationDataError('Each case must be a JSON object')
    required = ('case_id', 'actual_model_id', 'expected_model_id', 'dataset_id',
                'split_id', 'initial')
    absent = [key for key in required if key not in raw]
    if absent:
        raise EvaluationDataError(f'Missing case fields: {absent}')
    try:
        expected = catalog.get(raw['expected_model_id'])
    except Exception as exc:
        raise EvaluationDataError(f'Unknown expected model ID: {exc}') from exc
    expected_family = raw.get('expected_family_id', expected.family_id)
    if expected_family != expected.family_id:
        raise EvaluationDataError('Supplied expected family conflicts with canonical catalog')
    # For true out-of-catalog negative tests, the evaluator may know the actual
    # identity even though the runtime registry does not. Such cases require an
    # explicit actual_family_id and are NEVER passed to the inference request.
    try:
        actual = catalog.get(raw['actual_model_id'])
    except Exception:
        actual = None
    actual_family = raw.get('actual_family_id', actual.family_id if actual else None)
    if not isinstance(actual_family, str) or not actual_family.strip():
        raise EvaluationDataError('Out-of-catalog actual identity requires actual_family_id')
    if actual is not None and actual_family != actual.family_id:
        raise EvaluationDataError('Supplied actual family conflicts with canonical catalog')
    initial = _observation(raw['initial'])
    probes = {}
    for pid, obj in raw.get('replay_probes', {}).items():
        if not isinstance(pid, str) or not pid:
            raise EvaluationDataError('Replay probe IDs must be strings')
        observation = _observation(obj, probe_id=pid)
        if observation.prompt_id != pid:
            raise EvaluationDataError(f'Replay probe {pid!r} has inconsistent prompt ID')
        probes[pid] = observation
    for key in ('case_id', 'dataset_id', 'split_id'):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise EvaluationDataError(f'{key} must be a nonempty string')
    source_ids = raw.get('source_record_ids', [])
    if not isinstance(source_ids, list) or not all(isinstance(x, str) for x in source_ids):
        raise EvaluationDataError('source_record_ids must be a string list')
    request = FingerprintRequest(
        request_id=raw['case_id'], initial=initial,
        expected_model_id=raw['expected_model_id'], expected_family_id=expected_family,
        deployment_id=raw.get('deployment_id'), domain=raw.get('domain'))
    return EvaluationCase(
        case_id=raw['case_id'], request=request,
        actual_model_id=raw['actual_model_id'], actual_family_id=actual_family,
        dataset_id=raw['dataset_id'], split_id=raw['split_id'],
        replay_probes=probes, persona_id=raw.get('persona_id'),
        prompt_group_id=raw.get('prompt_group_id'), source_record_ids=source_ids)


def read_cases(path: str | Path, catalog: ModelCatalog, *, limit: int | None = None) -> list[EvaluationCase]:
    path = Path(path)
    if limit is not None and limit < 1:
        raise EvaluationDataError('limit must be >= 1')
    seen: set[str] = set()
    out: list[EvaluationCase] = []
    with path.open(encoding='utf-8') as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                case = parse_case(entry, catalog)
            except (ValueError, TypeError, KeyError) as exc:
                raise EvaluationDataError(f'{path}:{line_no}: {exc}') from exc
            if case.case_id in seen:
                raise EvaluationDataError(f'{path}:{line_no}: duplicate case_id {case.case_id!r}')
            seen.add(case.case_id)
            out.append(case)
            if limit is not None and len(out) >= limit:
                break
    if not out:
        raise EvaluationDataError(f'{path} has no evaluation cases')
    return out


def case_to_dict(case: EvaluationCase) -> dict:
    """Export normalized cases for deterministic replay; not for publishing raw data."""
    from dataclasses import asdict
    return {
        'case_id': case.case_id, 'expected_model_id': case.request.expected_model_id,
        'actual_model_id': case.actual_model_id, 'expected_family_id': case.request.expected_family_id,
        'actual_family_id': case.actual_family_id, 'dataset_id': case.dataset_id,
        'split_id': case.split_id, 'initial': asdict(case.request.initial),
        'replay_probes': {key: asdict(obs) for key, obs in case.replay_probes.items()},
        'persona_id': case.persona_id, 'prompt_group_id': case.prompt_group_id,
        'source_record_ids': list(case.source_record_ids), 'deployment_id': case.request.deployment_id,
        'domain': case.request.domain,
    }


def write_cases(cases: Iterable[EvaluationCase], destination: str | Path) -> None:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as stream:
        for case in cases:
            stream.write(json.dumps(case_to_dict(case), ensure_ascii=False) + '\n')


def dataset_profile(cases: list[EvaluationCase]) -> dict:
    """Report repeated source observations and cohort mix rather than hiding dependence."""
    return {
        'cases': len(cases),
        'unique_source_observations': len({tuple(x.source_record_ids) or (x.case_id,) for x in cases}),
        'per_dataset': dict(sorted(Counter(x.dataset_id for x in cases).items())),
        'per_split': dict(sorted(Counter(x.split_id for x in cases).items())),
        'per_persona': dict(sorted(Counter(x.persona_id or 'none' for x in cases).items())),
        'per_actual_model': dict(sorted(Counter(x.actual_model_id for x in cases).items())),
        'changed': sum(x.actual_model_id != x.request.expected_model_id for x in cases),
        'unchanged': sum(x.actual_model_id == x.request.expected_model_id for x in cases),
        'cases_with_complete_harness_probe_set': sum(
            {'LM-01','LM-05','LM-06','I1','I2','V1-15'} <= set(x.replay_probes) for x in cases),
        'cohorts_are_mixed': len({(x.dataset_id, x.split_id, x.persona_id) for x in cases}) > 1,
    }


def source_sha256(path: str | Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def convert_rf_holdout(path: str | Path, catalog: ModelCatalog, *, limit_per_model: int = 4,
                       seed: int = 42) -> list[EvaluationCase]:
    """Convert existing RF P13 *fixed-prompt* holdout into paired swap/no-swap cases.

    This is a PILOT convenience, not a new leakage-free multi-method holdout.
    No persona/probe data from a different deployment is joined to these records.
    """
    import random
    rng = random.Random(seed)
    per_model: dict[str, list[dict]] = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if not r.get('response_text') or not r.get('prompt'):
            continue
        catalog.get(r['model_key'])
        per_model.setdefault(r['model_key'], []).append(r)
    supported_s1 = ('llama3.1-8b', 'llama3.2-3b', 'gemini-3.1-pro', 'gemini-3.8-flash')
    out: list[EvaluationCase] = []
    for actual in sorted(per_model):
        records = sorted(per_model[actual], key=lambda r: (r['prompt_id'], r['record_id']))
        rng.shuffle(records)
        if limit_per_model:
            records = records[:limit_per_model]
        for r in records:
            rid = r['record_id']
            obs = Observation(
                r['prompt'], r['response_text'], r['prompt_id'],
                int(float(r['output_tokens'])) if r.get('output_tokens') not in (None, '') else None,
                float(r['latency_ms']) if r.get('latency_ms') not in (None, '') else None)
            # Stage 1 does not support all RF classes. Use a registered approved identity
            # when simulating swaps, and only create same-model cases when supported.
            choices = []
            if actual in supported_s1:
                choices.append(actual)
            swapped = next(m for m in supported_s1 if m != actual)
            choices.append(swapped)
            for expected in choices:
                ident = f'{rid}|approved={expected}'
                out.append(EvaluationCase(
                    case_id=ident,
                    request=FingerprintRequest(ident, obs, expected, catalog.get(expected).family_id),
                    actual_model_id=actual, actual_family_id=catalog.get(actual).family_id,
                    dataset_id='rf_fingerprint_v0', split_id='rf_fixed_prompt_holdout',
                    persona_id=r.get('persona_id'), prompt_group_id=r['prompt_id'],
                    source_record_ids=[rid], replay_probes={}))
    if not out:
        raise EvaluationDataError('No RF cases converted')
    return out
