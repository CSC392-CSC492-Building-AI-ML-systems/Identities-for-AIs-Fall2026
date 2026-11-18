"""Target chatbot adapters for the Stage 2 TargetClient protocol.

ReplayTargetClient (in strategies.py) uses recorded responses. CallableTargetClient
allows a backend to supply its own chatbot connection without importing API SDKs
or hardcoding a provider into the fingerprinting pipeline.
"""
from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from .schemas import Observation, ProbeQuestion


class CallableTargetClient:
    """Convert a `send_prompt(str) -> str` callable into a target LLM client.

    The supplied callable runs only when a probe is requested, and must return
    nonempty response text. Does not know model identities or evaluation truth.
    """

    def __init__(self, send_prompt: Callable[[str], str]):
        if not callable(send_prompt):
            raise TypeError('send_prompt must be callable')
        self.send_prompt = send_prompt

    def ask(self, probe: ProbeQuestion) -> Observation:
        started = perf_counter()
        text = self.send_prompt(probe.prompt_text)
        elapsed_ms = (perf_counter() - started) * 1000
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f'Target client returned no response to {probe.probe_id}')
        return Observation(probe.prompt_text, text, prompt_id=probe.probe_id,
                           latency_ms=elapsed_ms)
