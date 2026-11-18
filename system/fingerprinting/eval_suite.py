"""Unified evaluation suite over existing Strategy Pattern and Factory interfaces.

A single run can evaluate Stage 1, every selected Stage 2 method separately,
and the configured end-to-end pipeline. Unavailable artifacts are explicit;
partial E2E runs require opt-in and are never labelled as the full pipeline.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .config import PipelineConfig, Stage1Selection, Stage2Selection, Stage2MethodSelection
from .evaluation import EvaluationRunner, EvaluationReport
from .factory import PipelineFactory
from .pipeline import FingerprintPipeline
from .registry import ArtifactRegistry
from .schemas import EvaluationCase
from .eval_cases import dataset_profile

METHODS = ('lora', 'harness', 'random_forest')
SCOPE = ('stage1', 'stage2', 'e2e', 'all')


def _rehash(config: PipelineConfig) -> PipelineConfig:
    raw = json.dumps(config.snapshot(), sort_keys=True, separators=(',', ':')).encode('utf-8')
    return replace(config, config_sha256=hashlib.sha256(raw).hexdigest())


def with_stage2(config: PipelineConfig, choices: Sequence[Stage2MethodSelection],
                mode: str) -> PipelineConfig:
    if not choices or mode not in ('single', 'fallback', 'run_all'):
        raise ValueError('Invalid Stage 2 strategy override')
    if mode == 'single' and len(choices) != 1:
        raise ValueError('single requires one selected method')
    if len(set(x.adapter for x in choices)) != len(choices):
        raise ValueError('duplicate Stage 2 adapters')
    return _rehash(replace(config, stage2=Stage2Selection(mode, tuple(choices))))


def with_stage1_enabled(config: PipelineConfig, enabled: bool) -> PipelineConfig:
    """Toggle verification for E2E without changing registered classifiers."""
    if type(enabled) is not bool:
        raise ValueError('enabled must be a boolean')
    return _rehash(replace(config, stage1=replace(config.stage1, enabled=enabled)))


def with_stage1_approach(config: PipelineConfig, approach: str) -> PipelineConfig:
    return _rehash(replace(config, stage1=replace(config.stage1, approach=approach)))


def confidence_interval(k: int, n: int, z: float = 1.96) -> dict[str, float] | None:
    """Wilson binomial interval, appropriate only when sampling assumptions hold."""
    if n <= 0 or k < 0 or k > n:
        return None
    import math
    p = k / n
    denom = 1 + z*z / n
    center = (p + z*z/(2*n))/denom
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/denom
    return {'low': round(max(0.0, center-half), 4),
            'high': round(min(1.0, center+half), 4)}


def extras(report: EvaluationReport, cases: Sequence[EvaluationCase]) -> dict[str, Any]:
    """Add coverage, cohort and error diagnostics without mutating underlying metrics."""
    if report.scope == 'stage1':
        fam = [r for r in report.rows if r['family_prediction_correct'] is not None]
        return {
            'family_prediction_coverage': round(len(fam)/len(report.rows), 4) if report.rows else None,
            'true_drift_count': sum(r['true_change'] for r in report.rows),
            'false_verification_rate_on_changed': _fraction(
                sum(r['true_change'] and r['verdict']=='verified' for r in report.rows),
                sum(r['true_change'] for r in report.rows)),
            'false_mismatch_rate_on_unchanged': _fraction(
                sum(not r['true_change'] and r['verdict']=='mismatch' for r in report.rows),
                sum(not r['true_change'] for r in report.rows)),
        }
    if report.scope == 'stage2':
        total = len(report.rows)
        all_attempts = [a for r in report.rows for a in r['attempts']]
        missing = sum(a['outcome']=='error' and 'MissingProbe' in (a.get('reason') or '')
                      for a in all_attempts)
        return {'case_coverage_with_candidate': _fraction(
                    sum(any(a['candidate_model'] is not None for a in r['attempts']) for r in report.rows), total),
                'missing_replay_probe_errors': missing,
                'mock_judge_attempts': sum(a['method']=='harness' and
                                           a.get('diagnostics', {}).get('mock_judge') is True
                                           for a in all_attempts)}
    changed = [r for r in report.rows if r['true_change'] is True]
    unchanged = [r for r in report.rows if r['true_change'] is False]
    return {
        'false_verification_rate_on_changed': _fraction(
            sum(r['status']=='verified' for r in changed), len(changed)),
        'false_drift_alarm_rate_on_unchanged': _fraction(
            sum(r['status']=='drift_detected' for r in unchanged), len(unchanged)),
        'review_rate': _fraction(sum(r['status']=='needs_review' for r in report.rows), len(report.rows)),
        'stage2_invocation_rate': _fraction(sum(bool(r['attempted_methods']) for r in report.rows), len(report.rows)),
        'accepted_candidate_accuracy': _fraction(
            sum(r['exact_match'] for r in report.rows if r['resolved_by'] in METHODS),
            sum(r['resolved_by'] in METHODS for r in report.rows)),
        'per_dataset': {name: {'cases': len(rows),
                      'exact_model_accuracy': _fraction(sum(r['exact_match'] for r in rows), len(rows))}
                        for name, rows in _cohorts(report.rows, cases).items()},
    }


def _fraction(num: int, denom: int) -> float | None:
    return round(num/denom, 4) if denom else None


def _cohorts(rows: list[dict], cases: Sequence[EvaluationCase]) -> dict[str, list[dict]]:
    dataset = {c.case_id:c.dataset_id for c in cases}
    by: dict[str, list[dict]] = {}
    for row in rows:
        by.setdefault(dataset[row['case_id']], []).append(row)
    return by


def _record(report: EvaluationReport, cases: Sequence[EvaluationCase], config: PipelineConfig,
            registry: ArtifactRegistry, artifact_ids: list[str], *, mode: str) -> dict:
    meta = {a:registry.get(a).manifest_sha256 for a in artifact_ids}
    return {
        'status': 'completed_diagnostic_only' if mode == 'mock' and any(x.startswith('harness/') for x in artifact_ids) else 'completed',
        'scope': report.scope, 'strategy': report.strategy,
        'metrics': {**report.metrics, **extras(report, cases)},
        'rows': report.rows, 'config_sha256': config.config_sha256,
        'artifact_ids': artifact_ids, 'manifest_sha256': meta,
    }


def run_suite(cases: Sequence[EvaluationCase], config: PipelineConfig,
              registry: ArtifactRegistry, factory: PipelineFactory, *,
              scope: str = 'all', methods: Sequence[str] | None = None,
              stage2_mode: str | None = None,
              allow_partial_e2e: bool = False,
              judge_provider: str = 'mock',
              run_all_stage1_approaches: bool = False,
              use_stage1: bool | None = None) -> dict[str, Any]:
    """Execute selected scopes; every missing/incompatible model is reported.

    Production factory must run with require_ready=True. Never loosen readiness
    for real models; only synthetic unit tests use require_ready=False.
    """
    if scope not in SCOPE:
        raise ValueError(f'Invalid scope {scope}')
    if use_stage1 is not None:
        config = with_stage1_enabled(config, use_stage1)
    if methods is None:
        methods = tuple(m.adapter for m in config.stage2.methods)
    methods = tuple(methods)
    if not methods or any(m not in METHODS for m in methods) or len(set(methods)) != len(methods):
        raise ValueError('methods must be unique known Stage 2 identifiers')
    selected = [next((m for m in config.stage2.methods if m.adapter == name), None) for name in methods]
    if any(x is None for x in selected):
        raise ValueError('Requested method is absent from selected configuration')
    selected = [x for x in selected if x is not None]
    mode = stage2_mode or config.stage2.mode
    if mode == 'single' and len(selected) != 1:
        raise ValueError('single mode requires exactly one selected method')
    if factory.require_ready is False:
        # Test-only caller; never allow this as a substitute for real weights.
        pass
    reports: dict[str, dict] = {}
    blocks: dict[str, str] = {}
    readiness = {}
    for art in [config.stage1.artifact_id] + [m.artifact_id for m in selected]:
        state = registry.readiness(art)
        readiness[art] = {'ready': state.ready, 'details': str(state)}
    s1_art = config.stage1.artifact_id
    stage1_usable = readiness[s1_art]['ready'] or not factory.require_ready
    if scope in ('all', 'stage1'):
        if not stage1_usable:
            blocks['stage1'] = f'{s1_art}: artifact unavailable'
        else:
            approaches = ('hierarchy_hard_route', 'hierarchy_soft', 'ovr_direct') if run_all_stage1_approaches else (config.stage1.approach,)
            for approach in approaches:
                cfg = with_stage1_approach(config, approach)
                try:
                    result = EvaluationRunner.stage1(cases, factory.build_stage1(cfg))
                    reports[f'stage1/{approach}'] = _record(result, cases, cfg, registry, [s1_art], mode='none')
                except Exception as exc:
                    blocks[f'stage1/{approach}'] = f'{type(exc).__name__}: {exc}'
    available = []
    for choice in selected:
        if readiness[choice.artifact_id]['ready'] or not factory.require_ready:
            available.append(choice)
        elif scope in ('all', 'stage2'):
            blocks[f'stage2/{choice.adapter}'] = f'{choice.artifact_id}: artifact unavailable'
    if scope in ('all', 'stage2'):
        for item in selected:
            if item not in available:
                continue
            cfg = with_stage2(config, [item], 'single')
            try:
                report = EvaluationRunner.stage2(cases, factory.build_stage2(cfg))
                recorded = _record(report, cases, cfg, registry, [item.artifact_id], mode=judge_provider if item.adapter=='harness' else 'none')
                supported = set(registry.get(item.artifact_id).supported_models)
                eligible = [r for r in report.rows if r['actual_model'] in supported]
                ineligible = [r for r in report.rows if r['actual_model'] not in supported]
                cand_correct = sum(any(a['candidate_model'] == r['actual_model'] for a in r['attempts']) for r in eligible)
                cand_avail = sum(any(a['candidate_model'] is not None for a in r['attempts']) for r in eligible)
                recorded['metrics']['supported_identity_cases'] = len(eligible)
                recorded['metrics']['out_of_supported_identity_cases'] = len(ineligible)
                recorded['metrics']['candidate_top1_accuracy_on_supported_with_candidate'] = _fraction(cand_correct, cand_avail)
                recorded['metrics']['accepted_out_of_supported_identity_count'] = sum(r['accepted_model'] is not None for r in ineligible)
                if item.adapter == 'harness' and recorded['metrics']['missing_replay_probe_errors']:
                    recorded['status'] = 'incomplete_missing_probe_data'
                    recorded['note'] = 'One or more cases lack the required six recorded probes; results are NOT identification-accuracy evidence.'
                if item.adapter == 'harness' and judge_provider == 'mock':
                    recorded['note'] = (recorded.get('note','') + ' Mock judge runs are PLUMBING-ONLY: no identification-accuracy claim').strip()
                    recorded['metrics']['exact_accuracy_all_cases'] = None
                    recorded['metrics']['exact_accuracy_accepted'] = None
                    recorded['metrics']['candidate_top1_accuracy_on_supported_with_candidate'] = None
                    if 'harness' in recorded['metrics']['by_method']:
                        recorded['metrics']['by_method']['harness']['candidate_top1_accuracy'] = None
                        recorded['metrics']['by_method']['harness']['accepted_accuracy'] = None
                reports[f'stage2/{item.adapter}'] = recorded
            except Exception as exc:
                blocks[f'stage2/{item.adapter}'] = f'{type(exc).__name__}: {exc}'
    if scope in ('all', 'e2e'):
        missing = [x for x in selected if x not in available]
        if config.stage1.enabled and not stage1_usable:
            blocks['e2e'] = f'{s1_art}: Stage 1 artifact unavailable'
        elif missing and not allow_partial_e2e:
            blocks['e2e'] = 'Full configured pipeline unavailable: ' + ', '.join(x.artifact_id for x in missing)
        elif not available:
            blocks['e2e'] = 'No ready Stage 2 methods'
        else:
            choices = available if missing else selected
            effective_mode = mode
            if len(choices) == 1:
                effective_mode = 'single'
            cfg = with_stage2(config, choices, effective_mode)
            try:
                pipe = factory.build(cfg)
                report = EvaluationRunner.e2e(cases, pipe)
                record = _record(report, cases, cfg, registry,
                                 ([s1_art] if cfg.stage1.enabled else []) + [x.artifact_id for x in choices],
                                 mode=judge_provider if any(x.adapter=='harness' for x in choices) else 'none')
                record['partial_pipeline'] = bool(missing) or len(choices) < len(config.stage2.methods)
                record['omitted_methods'] = [x.adapter for x in config.stage2.methods if x not in choices]
                if record['partial_pipeline']:
                    record['note'] = 'Subset/partial E2E diagnostic; NOT full configured pipeline evaluation'
                if judge_provider == 'mock' and any(x.adapter == 'harness' for x in choices):
                    record['note'] = (record.get('note', '') + ' Harness mock is a plumbing diagnostic, NOT real judge accuracy.').strip()
                reports['e2e'] = record
            except Exception as exc:
                blocks['e2e'] = f'{type(exc).__name__}: {exc}'
    profiles = dataset_profile(list(cases))
    warnings = [
        'Ground truth is used only for scoring, never passed to models.',
        'Closed-set LoRA/RF candidates are NOT accepted while review_only; candidate accuracy differs from final resolution.',
        'The included RF P13 split reuses known prompts and backend features. It is NOT unseen-prompt, unseen-family or deployment-transfer validation.',
        'Confidence intervals assuming independent samples are not justified for repeated-source swap scenarios.',
    ]
    if profiles['cohorts_are_mixed']:
        warnings.append('Mixed cohorts detected: aggregate metrics are descriptive. Evaluate each dataset/split/persona separately for defensible comparisons.')
    if judge_provider == 'mock':
        warnings.append('Harness mock provider does not measure true judge accuracy; Harness outcomes are diagnostic only.')
    if blocks:
        warnings.append('Unavailable or failed scopes were recorded in blocked; their metrics were NOT imputed.')
    return {
        'schema_version': '1.0',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'config_sha256': config.config_sha256, 'config_selection': config.snapshot(),
        'requested': {'scope': scope, 'methods': list(methods), 'stage2_mode': mode,
                      'allow_partial_e2e': allow_partial_e2e,
                      'run_all_stage1_approaches': run_all_stage1_approaches,
                      'use_stage1': config.stage1.enabled,
                      'judge_provider': judge_provider},
        'dataset': profiles, 'artifact_readiness': readiness,
        'reports': reports, 'blocked': blocks, 'warnings': warnings,
    }


def _render_value(value: Any) -> str:
    return '—' if value is None else f'{value:.2%}' if isinstance(value, float) and 0 <= value <= 1 else str(value)


def save_suite(suite: dict, output_dir: str | Path, *, dataset_source: str | None = None,
               dataset_sha256: str | None = None) -> None:
    """Store machine-readable, tabular, and readable reports. No prompt text included."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    summary = {key: value for key, value in suite.items() if key != 'reports'}
    summary['dataset_source'] = dataset_source
    summary['dataset_sha256'] = dataset_sha256
    summary['report_files'] = []
    rows: list[dict] = []
    metric_rows = []
    for name, obj in suite['reports'].items():
        file = f'{name.replace("/", "_")}.json'
        (path / file).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
        summary['report_files'].append(file)
        for row in obj['rows']:
            rows.append({'scope': name, 'case_id': row.get('case_id'),
                         'actual_model': row.get('actual_model'),
                         'expected_model': row.get('expected_model'),
                         'verdict': row.get('verdict') or row.get('stage1_verdict'),
                         'status': row.get('status'),
                         'predicted_model': row.get('predicted_model') or row.get('accepted_model'),
                         'selected_method': row.get('selected_method') or row.get('resolved_by'),
                         'exact_match': row.get('exact_match'),
                         'attempted_methods': ','.join(row.get('attempted_methods', [])),
                         'attempts_json': json.dumps(row.get('attempts', row.get('stage2_attempts', [])), ensure_ascii=False, default=str),
                         'routing_trace': ','.join(row.get('routing_trace', []))})
        for metric, value in obj['metrics'].items():
            if isinstance(value, (dict, list)):
                continue
            metric_rows.append({'scope': name, 'metric': metric, 'value': value})
    (path / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str)+'\n', encoding='utf-8')
    for name, headers, data in (
        ('metrics.csv', ['scope', 'metric', 'value'], metric_rows),
        ('case_results.csv', ['scope','case_id','actual_model','expected_model','verdict','status',
                              'predicted_model','selected_method','exact_match','attempted_methods',
                              'attempts_json','routing_trace'], rows)):
        with (path / name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)
    txt = ['# Unified evaluation summary', '', f"Cases: **{suite['dataset']['cases']}**; unique source observations: **{suite['dataset']['unique_source_observations']}**",
           f"Stage 2 requested: {', '.join(suite['requested']['methods'])}; mode: {suite['requested']['stage2_mode']}", '',
           '## Completed evaluations', '']
    if not suite['reports']:
        txt.append('No evaluation scopes were completed.')
    for name, report in suite['reports'].items():
        txt += [f'### {name}', '', f"Status: `{report['status']}`. Artifacts: {', '.join(report['artifact_ids'])}.", '']
        if report.get('note'):
            txt += [f"**Limitation:** {report['note']}", '']
        for k, v in report['metrics'].items():
            if not isinstance(v, (dict,list)):
                txt.append(f'- {k}: {_render_value(v)}')
        txt.append('')
    txt += ['## Blocked or unavailable scopes', '']
    txt += [f'- `{key}`: {reason}' for key, reason in suite['blocked'].items()] or ['None']
    txt += ['', '## Interpretation warnings', '']
    txt += [f'- {warning}' for warning in suite['warnings']]
    txt += ['', 'Raw responses are intentionally omitted from case_results.csv. See dataset source for the original data.', '']
    (path / 'summary.md').write_text('\n'.join(txt), encoding='utf-8')
