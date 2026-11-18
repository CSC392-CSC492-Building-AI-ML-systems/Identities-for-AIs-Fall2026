"""Concrete Stage 2 Strategy Design Pattern implementations.

SingleMethodStrategy: force just one identifier (e.g. isolate LoRA).
FallbackStrategy: production LoRA -> Harness -> RF, stop on acceptance.
RunAllStrategy: evaluation-only, run every method and retain every result.

Nothing here loads real model weights or calls external APIs. All dependencies
are supplied by the caller and are mockable.
"""
from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from typing import Sequence

from .interfaces import Stage2Identifier, TargetClient
from .schemas import IdentificationInput, IdentificationResult, Observation, Stage2Run


class MissingProbeError(RuntimeError):
    pass


class ReplayTargetClient:
    """Replay prerecorded probe observations. Missing probes are explicit errors."""

    def __init__(self, observations: dict[str, Observation]):
        self.observations = dict(observations)
        self.asked: list[str] = []

    def ask(self, probe):
        self.asked.append(probe.probe_id)
        if probe.probe_id not in self.observations:
            raise MissingProbeError(f"No recorded answer for probe '{probe.probe_id}'")
        observation = self.observations[probe.probe_id]
        if observation.prompt_id is not None and observation.prompt_id != probe.probe_id:
            raise ValueError(f"Recorded observation has wrong prompt_id for '{probe.probe_id}'")
        return observation


def _run_methods(methods: Sequence[Stage2Identifier], strategy_name: str,
                 context: IdentificationInput, target_client: TargetClient | None,
                 stop_on_acceptance: bool) -> Stage2Run:
    start = perf_counter()
    attempts: list[IdentificationResult] = []
    probes: dict[str, Observation] = dict(context.probes)
    newly_collected: list[str] = []
    chosen_index: int | None = None

    for method in methods:
        method_start = perf_counter()
        try:
            for probe in method.required_probes():
                if probe.probe_id not in probes:
                    if target_client is None:
                        raise MissingProbeError(f"No client for required probe '{probe.probe_id}'")
                    probes[probe.probe_id] = target_client.ask(probe)
                    newly_collected.append(probe.probe_id)
            # Neither expected nor ground-truth model identity is ever passed here.
            per_method_context = IdentificationInput(
                initial=context.initial, probes=dict(probes),
                deployment_id=context.deployment_id, domain=context.domain)
            result = method.identify(per_method_context)
            if result.method != method.name:
                raise ValueError(f"{method.name} returned result for method {result.method}")
            if result.duration_ms is None:
                result = replace(result, duration_ms=(perf_counter() - method_start) * 1000)
        except Exception as exc:
            result = IdentificationResult(
                method=method.name, outcome="error", reason=f"{type(exc).__name__}: {exc}",
                duration_ms=(perf_counter() - method_start) * 1000,
                diagnostics={"exception_type": type(exc).__name__})
        attempts.append(result)
        if (result.outcome == "identified" and result.accepted_model_id is not None
                and result.handoff_requested is not True and chosen_index is None):
            chosen_index = len(attempts) - 1
            if stop_on_acceptance:
                break

    return Stage2Run(
        strategy=strategy_name, attempts=attempts, selected_attempt_index=chosen_index,
        probe_ids_collected=newly_collected,
        duration_ms=(perf_counter() - start) * 1000)


def _validate_identifiers(identifiers: Sequence[Stage2Identifier]) -> tuple[Stage2Identifier, ...]:
    methods = tuple(identifiers)
    if not methods:
        raise ValueError("Strategy requires at least one identifier")
    names = [m.name for m in methods]
    if len(set(names)) != len(names):
        raise ValueError(f"Duplicate Stage 2 method names: {names}")
    if any(name not in ("lora", "harness", "random_forest") for name in names):
        raise ValueError(f"Invalid Stage 2 method names: {names}")
    return methods


class SingleMethodStrategy:
    def __init__(self, identifier: Stage2Identifier):
        self.identifiers = _validate_identifiers([identifier])
        self.name = f"only_{identifier.name}"

    def execute(self, context: IdentificationInput, target_client: TargetClient | None = None) -> Stage2Run:
        return _run_methods(self.identifiers, self.name, context, target_client, True)


class FallbackStrategy:
    def __init__(self, identifiers: Sequence[Stage2Identifier]):
        self.identifiers = _validate_identifiers(identifiers)
        self.name = "fallback_" + "_then_".join(m.name for m in self.identifiers)

    def execute(self, context: IdentificationInput, target_client: TargetClient | None = None) -> Stage2Run:
        return _run_methods(self.identifiers, self.name, context, target_client, True)


class RunAllStrategy:
    """Comparison experiment only. Does not stop on acceptance; first accepted wins."""

    def __init__(self, identifiers: Sequence[Stage2Identifier]):
        self.identifiers = _validate_identifiers(identifiers)
        self.name = "compare_all_" + "_".join(m.name for m in self.identifiers)

    def execute(self, context: IdentificationInput, target_client: TargetClient | None = None) -> Stage2Run:
        return _run_methods(self.identifiers, self.name, context, target_client, False)
