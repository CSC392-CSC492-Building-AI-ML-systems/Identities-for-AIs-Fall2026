"""Production-facing fingerprinting orchestrator; Stage 2 is the default path.

Stage 1 is opt-in per configuration or per invocation. No ground truth here.
"""
from __future__ import annotations

from dataclasses import replace
from threading import Lock
from time import perf_counter
from typing import Callable

from .interfaces import CardResolver, Stage1Strategy, Stage2Strategy, TargetClient
from .schemas import FinalResult, FingerprintRequest, IdentificationInput, PipelineResult, Stage1Result


class FingerprintPipeline:
    """Uses injected strategies; chooses whether to execute Stage 1, not their internals.

    Passing a Stage 1 strategy directly counts as explicit opt-in for legacy callers.
    Factory-built pipelines use stage1_enabled=False by default and a lazy loader.
    """

    def __init__(self, stage1: Stage1Strategy | None, stage2: Stage2Strategy,
                 cards: CardResolver | None = None, *,
                 stage1_enabled: bool | None = None,
                 stage1_loader: Callable[[], Stage1Strategy] | None = None,
                 config_sha256: str | None = None,
                 artifact_ids: dict[str, str] | None = None,
                 manifest_sha256: dict[str, str] | None = None):
        self.stage1 = stage1
        self.stage2 = stage2
        self.cards = cards
        # Direct construction with a Stage 1 object is explicit use (legacy API).
        self.stage1_enabled = (stage1 is not None) if stage1_enabled is None else stage1_enabled
        self._stage1_loader = stage1_loader
        self._stage1_lock = Lock()
        self.config_sha256 = config_sha256
        self.artifact_ids = dict(artifact_ids or {})
        self.manifest_sha256 = dict(manifest_sha256 or {})

    def _get_stage1(self) -> Stage1Strategy:
        if self.stage1 is None:
            with self._stage1_lock:
                if self.stage1 is None:
                    if self._stage1_loader is None:
                        raise RuntimeError('Stage 1 is unavailable; configure a Stage 1 adapter before enabling it')
                    self.stage1 = self._stage1_loader()
        return self.stage1

    def run(self, request: FingerprintRequest,
            target_client: TargetClient | None = None, *,
            use_stage1: bool | None = None) -> PipelineResult:
        """Run Stage 2 normally; pass use_stage1=True to opt into verification.

        If Stage 1 is requested, both expected IDs are required. Stage 2 does not
        require them. Stage 1 loading is deferred until the first enabled call.
        """
        start = perf_counter()
        trace: list[str] = []
        active = self.stage1_enabled if use_stage1 is None else use_stage1
        if type(active) is not bool:
            raise ValueError('use_stage1 must be a boolean or None')
        if active and (request.expected_model_id is None or request.expected_family_id is None):
            raise ValueError('Stage 1 requires expected_model_id and expected_family_id')
        name2 = getattr(self.stage2, 'name', type(self.stage2).__name__)
        if active:
            # Missing/unready Stage 1 resources are configuration problems, not
            # evidence of model drift. Do not quietly claim Stage 1 was skipped.
            strategy = self._get_stage1()
            name1 = getattr(strategy, 'name', type(strategy).__name__)
            stage1_start = perf_counter()
            try:
                s1 = strategy.verify(request)
                if not isinstance(s1, Stage1Result):
                    raise TypeError('Stage1 strategy must return Stage1Result')
                if s1.verdict == 'verified' and (s1.family_match is not True or s1.model_match is not True):
                    raise ValueError('Stage 1 verified requires family_match=True and model_match=True')
            except Exception as exc:
                s1 = Stage1Result(verdict='error', reason=f'{type(exc).__name__}: {exc}')
            if s1.duration_ms is None:
                s1 = replace(s1, duration_ms=(perf_counter() - stage1_start) * 1000)
            trace.append(f'stage1:{name1}:{s1.verdict}')
            if s1.verdict == 'verified':
                final = FinalResult('verified', request.expected_model_id, 'stage1',
                                    'Stage 1 verified both expected identity checks')
                return self._finish(request, s1, [], final, trace, start, name1, name2, active)
        else:
            name1 = None
            s1 = Stage1Result(verdict='skipped', reason='Stage 1 disabled (default); Stage 2 runs directly')
            trace.append('stage1:skipped')

        trace.append('stage2:entered')
        try:
            s2 = self.stage2.execute(
                IdentificationInput(initial=request.initial,
                                    deployment_id=request.deployment_id, domain=request.domain),
                target_client)
            if s2.accepted_model_id is not None:
                model_id = s2.accepted_model_id
                if request.expected_model_id is None:
                    status, reason = 'identified', 'Stage 2 accepted a model identity; no expected model provided'
                elif model_id == request.expected_model_id:
                    status, reason = 'verified', 'Accepted Stage 2 model matches expected identity'
                else:
                    status, reason = 'drift_detected', 'Accepted Stage 2 model differs from expected identity'
                final = FinalResult(status, model_id, s2.resolved_by, reason)
            elif s2.attempts and all(a.outcome == 'error' for a in s2.attempts):
                final = FinalResult('error', None, None, 'All Stage 2 methods failed to execute')
            else:
                final = FinalResult('needs_review', None, None, 'No Stage 2 method accepted an exact identity')
            trace.extend(f'stage2:{a.method}:{a.outcome}' for a in s2.attempts)
            trace.append(f'stage2:accepted:{s2.resolved_by}' if s2.resolved_by else 'stage2:unresolved')
            attempts = s2.attempts
        except Exception as exc:
            final = FinalResult('error', None, None, f'Stage 2 strategy failed: {type(exc).__name__}: {exc}')
            attempts = []
            trace.append('stage2:strategy_error')
        return self._finish(request, s1, attempts, final, trace, start, name1, name2, active)

    def _finish(self, request, stage1, attempts, final, trace, start, name1, name2, active):
        card = None
        if self.cards is not None and final.model_id is not None:
            try:
                card = self.cards.resolve(final.model_id, request.domain)
            except Exception as exc:
                trace.append(f'card:lookup_error:{type(exc).__name__}')
        return PipelineResult(
            request_id=request.request_id, stage1=stage1, stage1_enabled=active,
            stage2_attempts=attempts, final=final, domain_card=card,
            stage1_strategy=name1, stage2_strategy=name2,
            routing_trace=trace, duration_ms=(perf_counter() - start) * 1000,
            config_sha256=self.config_sha256, artifact_ids=dict(self.artifact_ids),
            manifest_sha256=dict(self.manifest_sha256))
