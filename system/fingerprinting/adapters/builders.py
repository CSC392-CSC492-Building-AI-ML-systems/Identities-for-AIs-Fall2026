"""Explicit trusted constructor registration for all four versioned real adapters.

The Factory can build standalone Stage 1, standalone Stage 2, or the complete
pipeline from YAML. No dynamic imports are specified in the configuration.
"""
from __future__ import annotations
from ..factory import AdapterConstructors
from .logistic_regression import build_logistic_regression
from .lora import build_lora
from .harness import HarnessIdentifier
from .random_forest import build_random_forest


def real_adapter_constructors(*, harness_judge_provider: str | None = None) -> AdapterConstructors:
    constructors = AdapterConstructors()
    constructors.register_stage1('logistic_regression', build_logistic_regression)
    constructors.register_stage2('lora', build_lora)
    constructors.register_stage2('harness',
        lambda manifest, choice: HarnessIdentifier(manifest, judge_provider=harness_judge_provider))
    constructors.register_stage2('random_forest', build_random_forest)
    return constructors
