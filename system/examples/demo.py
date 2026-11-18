"""Run a complete MOCK pipeline and evaluate one case. No real model calls."""
import json
import sys
from pathlib import Path

# Allow `python examples/demo.py` from the checkout without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fingerprinting.schemas import (EvaluationCase, FingerprintRequest,
    IdentificationResult, Observation, Stage1Result)
from fingerprinting.pipeline import FingerprintPipeline
from fingerprinting.strategies import FallbackStrategy, SingleMethodStrategy
from fingerprinting.testing import StubIdentifier, StubStage1
from fingerprinting.evaluation import EvaluationRunner

obs = Observation("Why do leaves change color?", "Leaves contain pigments.", "demo-q")
req = FingerprintRequest("demo-001", obs, "llama3.1-8b", "llama")
s1 = StubStage1("hierarchical_hard_route_mock", Stage1Result("mismatch", family_match=True, model_match=False))
lora = StubIdentifier("lora", IdentificationResult("lora", "unknown", candidate_model_id="llama3.2-3b"))
harness = StubIdentifier("harness", IdentificationResult("harness", "identified",
    candidate_model_id="llama3.2-3b", accepted_model_id="llama3.2-3b"))
rf = StubIdentifier("random_forest", IdentificationResult("random_forest", "identified",
    candidate_model_id="llama3.1-8b", accepted_model_id="llama3.1-8b"))

pipeline = FingerprintPipeline(s1, FallbackStrategy([lora, harness, rf]))
print("Pipeline result (MOCK):")
print(json.dumps(pipeline.run(req).to_dict(), indent=2))

case = EvaluationCase("demo-001", req, "llama3.2-3b", "llama", "demo", "test")
print("\nIndividual LoRA-only evaluation (MOCK):")
print(json.dumps(EvaluationRunner.stage2([case], SingleMethodStrategy(lora)).metrics, indent=2))
print("\nEnd-to-end evaluation (MOCK):")
print(json.dumps(EvaluationRunner.e2e([case], pipeline).metrics, indent=2))
