# Unified Evaluation — current guide

**November 18, 2026.** This guide describes the current evaluation subsystem. Historical instructions from before the LoRA v2 checkpoint was installed are in [UNIFIED_EVALUATION_HISTORY.md](UNIFIED_EVALUATION_HISTORY.md).

The evaluation runner scores Stage 1, individual Stage 2 methods, configured fallback and E2E workflows using `EvaluationCase` ground truth **only for evaluation**, never for inference. The new one-prompt `PromptAnalysisService` is a **runtime composition layer**, not a substitute for a frozen, leakage-checked evaluation dataset.

## Commands from the GitHub repository root

```bash
python -m pip install -r system/requirements-integrated.txt
python system/run.py test
python system/run.py config --require-ready

# Pilot evaluation only; previously seen prompt IDs / different test regimes:
python system/run.py evaluate --rf-pilot --scope stage1 --all-stage1-approaches
python system/run.py evaluate --rf-pilot --scope stage2 --methods random_forest
python system/run.py evaluate --rf-pilot --scope e2e --methods random_forest

# Full configured Stage 2 selection (LoRA v2, Harness, Random Forest):
# Will attempt actual LoRA inference and may invoke Harness judge; verify
# dependencies, privacy permission, compute and provider settings first.
# DO NOT treat mock judge outcomes as real identification-accuracy evidence.
```

## Readiness and caveats

- `system/models/lora/v2/` now has the real supplied five-class checkpoint, checksummed files and a Qwen2.5-0.5B base-model declaration. **Artifact readiness is true**, but actual GPU/CPU inference parity, label order and base revision are not yet validated. Python dependencies `transformers`, `peft`, `accelerate`, `torch` and base weights are separate. `lora/v1` remains historically incomplete.
- LoRA v2 operates in **review_only** mode and withholds named candidates while class labels are unverified; RF v1 returns ranked candidates but no accepted identity or change assertion. A score is not a calibrated probability of being correct.
- Harness mock judge validates processing and probe plumbing, not model-identification accuracy. Live judge tests need explicit provider setup, consent, credentials and cost limits.
- Existing Stage 1 checks only four Gemini/Llama IDs. It is opt-in by configuration or `--use-stage1` and may mistakenly verify changes; report false verifications separately.
- The RF fixed-prompt P13 pilot uses 52 features including prompt ID, output tokens and latency; its historical ~93% top-1 score is **not** unseen-prompt or deployment-transfer accuracy. LoRA teammate's historical ~67.6% score used a different data split and checkpoint; do not attribute it to imported v2.
- E2E metrics require a shared disjoint held-out dataset, complete Harness probe replays, unknown-class negatives and a validated accept/reject policy. Do not interpret successful runner execution as a scientifically valid production result.

Use `system/TBD.md` for current blockers, calibration and publication requirements.
