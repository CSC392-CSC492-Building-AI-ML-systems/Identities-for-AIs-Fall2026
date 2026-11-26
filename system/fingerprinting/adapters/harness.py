"""Versioned adapter for Stage 2B's original six-probe AI Harness.

All judge and post-processing logic stays in the original source snapshot.
The subprocess isolates the legacy modules and permits different Harness
versions to be invoked in the same evaluation session without import clashes.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from time import perf_counter
from typing import Any

from ..config import Stage2MethodSelection
from ..registry import ArtifactManifest
from ..schemas import IdentificationInput, IdentificationResult, ProbeQuestion

PROVIDERS = frozenset({'google', 'anthropic', 'openai', 'mock'})
RESULT_MARKER = '__FINGERPRINTING_HARNESS_RESULT__='
Runner = Callable[[dict[str, Any]], Mapping[str, Any]]


class HarnessConfigurationError(ValueError):
    pass


class HarnessExecutionError(RuntimeError):
    pass


class HarnessIdentifier:
    name = 'harness'

    def __init__(self, manifest: ArtifactManifest, *, judge_provider: str | None = None,
                 runner: Runner | None = None):
        if manifest.adapter != 'harness' or manifest.stage != 2:
            raise HarnessConfigurationError('Expected a Stage 2 harness manifest')
        self.manifest = manifest
        self.artifact_id = manifest.artifact_id
        self.provider = judge_provider or manifest.options.get('judge_provider', 'google')
        if self.provider not in PROVIDERS:
            raise HarnessConfigurationError(f'Unknown Harness judge provider: {self.provider}')
        self.judge_model = manifest.options.get('judge_model')
        if not isinstance(self.judge_model, str) or not self.judge_model:
            raise HarnessConfigurationError('Harness manifest needs a judge_model')
        self.handoff_below = manifest.options.get('handoff_below')
        if (isinstance(self.handoff_below, bool) or not isinstance(self.handoff_below, (int, float))
                or not math.isfinite(self.handoff_below) or not 0.0 <= self.handoff_below <= 1.0):
            raise HarnessConfigurationError('Invalid handoff_below')
        self.timeout_seconds = manifest.options.get('timeout_seconds', 240)
        if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                or not 0 < self.timeout_seconds <= 1200):
            raise HarnessConfigurationError('Invalid timeout_seconds')
        self.probe_ids = manifest.options.get('probe_ids')
        if (not isinstance(self.probe_ids, list) or len(self.probe_ids) != 6
                or len(set(self.probe_ids)) != 6 or any(not isinstance(x, str) for x in self.probe_ids)):
            raise HarnessConfigurationError('Harness requires six unique probe IDs')
        self.review_only = manifest.options.get('reference_abi') == 'catalog_reference_v2'
        if self.review_only and self.provider not in ('google','openai','mock'):
            raise HarnessConfigurationError('Unsupported v2 judge transport')
        expected_policy = 'review_only' if self.review_only else 'legacy_handoff_and_exact_model'
        if manifest.options.get('acceptance_policy') != expected_policy:
            raise HarnessConfigurationError('Unrecognized Harness acceptance policy')
        self._runner = runner
        # Keep the exact prompt definitions bound to the version's reference snapshot.
        import yaml
        path = manifest.directory / 'collector/prompts/fingerprinting_prompts.yaml'
        if not path.is_file():
            raise HarnessConfigurationError(f'Missing versioned Harness prompt file: {path}')
        prompt_data = yaml.safe_load(path.read_text(encoding='utf-8'))
        if not isinstance(prompt_data, dict) or not isinstance(prompt_data.get('prompts'), list):
            raise HarnessConfigurationError('Malformed Harness prompt YAML')
        prompts = {p['id']: p['text'] for p in prompt_data['prompts'] if isinstance(p, dict) and
                   isinstance(p.get('id'), str) and isinstance(p.get('text'), str)}
        missing = set(self.probe_ids) - prompts.keys()
        if missing:
            raise HarnessConfigurationError(f'Harness prompt definitions missing: {sorted(missing)}')
        self._probes = tuple(ProbeQuestion(pid, prompts[pid]) for pid in self.probe_ids)

    def required_probes(self) -> tuple[ProbeQuestion, ...]:
        return self._probes

    def _run_legacy(self, payload: dict[str, Any]) -> dict[str, Any]:
        worker = Path(__file__).with_name('harness_worker.py')
        try:
            process = subprocess.run(
                [sys.executable, "-B", str(worker), str(self.manifest.directory)],
                input=json.dumps(payload, ensure_ascii=False), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=float(self.timeout_seconds), check=False,
                cwd=str(self.manifest.directory / 'agent'),
            )
        except subprocess.TimeoutExpired as exc:
            raise HarnessExecutionError('Harness worker timed out') from exc
        if process.returncode != 0:
            # Avoid echoing probe responses or entire stack traces in error messages.
            if self.review_only:
                raise HarnessExecutionError(f'Harness worker failed (exit {process.returncode}); check judge setup locally')
            raise HarnessExecutionError(f'Harness worker failed (exit {process.returncode}); '
                                        f'{process.stderr.strip()[-350:]}')
        lines = [x[len(RESULT_MARKER):] for x in process.stdout.splitlines()
                 if x.startswith(RESULT_MARKER)]
        if len(lines) != 1:
            raise HarnessExecutionError('Harness worker did not emit exactly one result')
        data = json.loads(lines[0])
        if not isinstance(data, dict):
            raise HarnessExecutionError('Harness worker result must be a JSON object')
        return data

    def identify(self, context: IdentificationInput) -> IdentificationResult:
        start = perf_counter()
        missing = [p.probe_id for p in self._probes if p.probe_id not in context.probes]
        if missing:
            raise ValueError(f'Missing Harness probe answers: {missing}')
        for p in self._probes:
            obs = context.probes[p.probe_id]
            if obs.prompt_id is not None and obs.prompt_id != p.probe_id:
                raise ValueError(f'Probe {p.probe_id} has an inconsistent prompt_id')
            if obs.prompt_text.strip() != p.prompt_text.strip():
                raise ValueError(f'Probe {p.probe_id} has a different prompt text from artifact')
        if context.deployment_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', context.deployment_id):
            raise ValueError('deployment_id must be 1-80 alphanumeric, underscore, or hyphen characters')
        payload = {
            'answers': {p.probe_id: context.probes[p.probe_id].response_text for p in self._probes},
            'domain': context.domain,
            'deployment': None if self.review_only else context.deployment_id,
            'judge_provider': self.provider,
            'judge_model': self.judge_model,
            'handoff_below': float(self.handoff_below),
        }
        data = dict(self._runner(payload)) if self._runner else self._run_legacy(payload)
        info = data.get('identified')
        if not isinstance(info, dict):
            raise HarnessExecutionError('Harness returned no identified object')
        model_key = info.get('model_key')
        if model_key is not None and model_key not in self.manifest.supported_models:
            raise HarnessExecutionError(f'Harness returned unregistered model ID: {model_key}')
        raw_fit = data.get('fit_score')
        if raw_fit is not None and (isinstance(raw_fit, bool) or not isinstance(raw_fit, (float, int))
                                    or not math.isfinite(raw_fit) or not 0 <= raw_fit <= 1):
            raise HarnessExecutionError('Harness returned an invalid fit_score')
        legacy_handoff = data.get('handoff_to_next_method')
        if not isinstance(legacy_handoff, bool):
            raise HarnessExecutionError('Harness must return Boolean handoff_to_next_method')
        status = data.get('status')
        if status not in ('Identified', 'Unknown model', 'Verified', 'Drift detected', 'Needs review'):
            raise HarnessExecutionError(f'Unexpected Harness status: {status!r}')
        # Mock judge is for plumbing only, NEVER an accepted production identity.
        accepted = bool(model_key and not legacy_handoff and status in ('Identified', 'Verified')
                        and self.provider != 'mock' and not self.review_only)
        reasons = data.get('reasons') or []
        if not isinstance(reasons, list):
            raise HarnessExecutionError('Harness reasons must be a list')
        diag: dict[str, Any] = {
            'artifact_id': self.artifact_id,
            'judge_provider': self.provider,
            'legacy_status': status,
            'legacy_handoff': legacy_handoff,
            'legacy_identified': info,
            'legacy_judge': data.get('judge'),
            'mock_judge': self.provider == 'mock',
            'review_only': self.review_only,
        }
        if 'card' in data and not self.review_only:
            diag['card'] = data['card']
        return IdentificationResult(
            method='harness', outcome='identified' if accepted else 'unknown',
            candidate_model_id=model_key, accepted_model_id=model_key if accepted else None,
            score=float(raw_fit) if raw_fit is not None else None,
            score_type='fit_score' if raw_fit is not None else None,
            handoff_requested=not accepted,
            probe_ids_used=list(self.probe_ids),
            reason='; '.join(str(r) for r in reasons) or
                   ('Accepted by legacy Harness' if accepted else 'Harness could not confirm an exact model'),
            duration_ms=(perf_counter() - start) * 1000,
            diagnostics=diag,
        )


def build_harness(manifest: ArtifactManifest, selection: Stage2MethodSelection) -> HarnessIdentifier:
    if selection.adapter != 'harness' or selection.artifact_id != manifest.artifact_id:
        raise HarnessConfigurationError('Harness builder selection mismatch')
    return HarnessIdentifier(manifest)
