"""Deterministic test doubles ONLY. These are not trained classifiers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .schemas import (FingerprintRequest, IdentificationInput,
                      IdentificationResult, ProbeQuestion, Stage1Result)


@dataclass
class StubStage1:
    name: str
    result: Stage1Result
    calls: list[FingerprintRequest] = field(default_factory=list)

    def verify(self, request: FingerprintRequest) -> Stage1Result:
        self.calls.append(request)
        return self.result


@dataclass
class StubIdentifier:
    name: str
    result: IdentificationResult
    probes: Sequence[ProbeQuestion] = ()
    calls: list[IdentificationInput] = field(default_factory=list)

    def required_probes(self):
        return self.probes

    def identify(self, context: IdentificationInput) -> IdentificationResult:
        self.calls.append(context)
        return self.result
