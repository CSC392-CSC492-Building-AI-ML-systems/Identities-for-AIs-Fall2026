"""Mock-score LoRA integration demo; NOT trained LoRA predictions.

The real PEFT weights are not included. This demonstrates independent Stage 2
configuration and output mapping without pretending that weights were loaded.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fingerprinting.adapters.lora import LoRAIdentifier
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import IdentificationInput, Observation

catalog = ModelCatalog.from_file(ROOT / 'catalog/models.json')
registry = ArtifactRegistry(ROOT, catalog)
cfg = load_pipeline_config(ROOT / 'config/experiments/lora_only.yaml', registry)
constructors = AdapterConstructors()
constructors.register_stage2('lora', lambda manifest, choice: LoRAIdentifier(
    manifest, predictor=lambda text: [0.05, 0.75, 0.1, 0.08, 0.02]))
# Test-only: no weights are loaded; do not use this configuration for real inference.
strategy = PipelineFactory(registry, constructors, require_ready=False).build_stage2(cfg)
run = strategy.execute(IdentificationInput(initial=Observation('Who made you?', 'I am...')))
print('Mock score demo: ', run.attempts[0])
print('Accepted:', run.accepted_model_id, '(expected: None until validated)')
