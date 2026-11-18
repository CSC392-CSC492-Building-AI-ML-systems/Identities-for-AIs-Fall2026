"""Prompt-only flow with a MOCK target and MOCK identifier. No API calls/accuracy claim.

From repository root: python system/run.py example prompt_workflow_mock_demo
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fingerprinting.clients import CallableTargetClient
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.pipeline import FingerprintPipeline
from fingerprinting.schemas import IdentificationResult
from fingerprinting.strategies import SingleMethodStrategy
from fingerprinting.testing import StubIdentifier
from fingerprinting.workflow import BaselineSnapshot, PromptAnalysisService

# Backend replaces this with an authorized provider SDK connection. There is no
# API key here and the response is synthetic, not a model fingerprint.
client = CallableTargetClient(lambda prompt: 'Synthetic test reply for: ' + prompt)
identifier = StubIdentifier('random_forest', IdentificationResult(
    method='random_forest', outcome='unknown', candidate_model_id='llama3.1-8b',
    reason='Mock candidate, not accepted'))
pipeline = FingerprintPipeline(None, SingleMethodStrategy(identifier), stage1_enabled=False)
service = PromptAnalysisService(pipeline, ModelCatalog.from_file(ROOT / 'catalog/models.json'))
report = service.analyze('Explain recursion in Python.', client,
                         request_id='mock-request', baseline=BaselineSnapshot('llama3.1-8b'))
print(json.dumps(report.to_dict(), indent=2))
