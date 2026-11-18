"""The Strategy Design Pattern contracts for verification and identification.

All interfaces are dependency-free; trained-model adapters implement these later.
"""
from __future__ import annotations

from typing import Protocol, Sequence
from .schemas import (FingerprintRequest, IdentificationInput, IdentificationResult,
                      Observation, ProbeQuestion, Stage1Result, Stage2Run)


class Stage1Strategy(Protocol):
    """Interchangeable implementation of Stage 1 verification."""

    name: str

    def verify(self, request: FingerprintRequest) -> Stage1Result:
        ...


# Backwards-compatible conceptual alias from contracts v1.
Stage1Verifier = Stage1Strategy


class Stage2Identifier(Protocol):
    """An algorithm, not a routing policy (LoRA, Harness, or RF)."""

    name: str

    def required_probes(self) -> Sequence[ProbeQuestion]:
        ...

    def identify(self, context: IdentificationInput) -> IdentificationResult:
        ...


class TargetClient(Protocol):
    """Live client or offline replay provider for Stage 2 probes."""

    def ask(self, probe: ProbeQuestion) -> Observation:
        ...


class Stage2Strategy(Protocol):
    """Selects which Stage 2 identifiers run and when to stop."""

    name: str

    def execute(self, context: IdentificationInput,
                target_client: TargetClient | None = None) -> Stage2Run:
        ...


class CardResolver(Protocol):
    """Last-mile enrichment, not part of model identification."""

    def resolve(self, model_id: str, domain: str | None = None) -> dict | None:
        ...
