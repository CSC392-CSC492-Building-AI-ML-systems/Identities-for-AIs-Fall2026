> **Current update:** RF, LoRA and Harness strategies are registered; Stage 1 is deferred, and the training CLI reports `blocked_stage1_deferred` for it. See [Harness reference builder](HARNESS_REFERENCE_BUILDER.md). Historical examples below (including `nov26_candidate.json`) are not current executable recipes. Use each method-specific configuration with a new artifact ID.

> **Current update:** RF and LoRA training strategies are registered. See [LoRA training](LORA_TRAINING.md). Harness and Stage 1 trainers remain pending. Historical generic examples below may be blocked.

# Training orchestration — prototype foundation (November 26, 2026)

The shared lifecycle now supports real fixed-probe Random Forest training. See
[RF_MULTI_PROMPT.md](RF_MULTI_PROMPT.md). LoRA, Harness and Stage 1 trainers
remain unavailable. The previous generic unseen-prompt split is not compatible
with the fixed-probe RF trainer; use a verified persona-holdout panel split.
No production config, authentication or confidence policy changed.

## Workflow

1. Register a raw snapshot and generate a candidate split using dataset onboarding.
2. Review quality, privacy/licences, label coverage, prompt grouping and historical
   leakage. The new policy includes blanks without errors; do not mistake blanks
   for confirmed refusals or replace them with reasoning text.
3. Select a training configuration. The orchestrator verifies the immutable raw
   snapshot, reconstructs and verifies split assignments, checks output version
   collisions, and reports available/blocked methods.
4. Explicitly approve an experimental run. Only train and validation rows are
   exported for the method-specific trainer. No test or calibration export is
   provided. Trusted trainer code must not use validation to fit or access the
   held-out data separately. No sandbox or independent-holdout certification.
5. The trainer produces a candidate manifest and declared payload files, including
   its actual code/dependencies and validation evidence. Orchestrator binds the
   dataset/split hash, eligibility policy and training run ID; checks source inputs
   remain intact and verifies the candidate through existing artifact onboarding.
6. Optional `--register-candidates` registers successful candidates through the
   existing registry. No production selection or reviewed baseline is changed.
   Use the existing candidate-config/evaluator to perform independent runtime and
   scientific validation before any manual activation.

## Commands (Windows Git Bash, repo root)

```bash
source .venv/Scripts/activate
python system/run.py training methods
python system/run.py training plan --config config/training/nov26_candidate.json
python system/run.py training plan --config config/training/nov26_candidate.json --method random_forest
python system/run.py training history
```

`run.py` interprets paths relative to `system/`; direct `tools/*.py` commands
interpret file arguments relative to the shell. Config is JSON (no arbitrary code
imports or shell commands). The supplied config has deliberately empty parameters;
replace with trainer-specific settings once they are known. IDs are proposed new
versions, not published artifacts. Change the ID if a teammate has published it.

Once a trusted trainer is wired into `available_trainers()`:

```bash
# One selected method, manually configured
python system/run.py training run --config config/training/nov26_candidate.json \
  --method random_forest --approve-dataset
# All configured methods in one batch, optional candidate registration
python system/run.py training run --config config/training/nov26_candidate.json \
  --approve-dataset --register-candidates
```

**The historical generic config remains blocked** (incompatible split protocol
or existing artifact ID). Use `config/training/rf_panel_candidate.json` as a
reference and create a new configuration with an unused artifact ID for training. A batch with some available methods runs those methods and
reports blocked methods; partial completion also returns status 2. No mock
training is installed in the CLI. An event-driven automatic trigger from dataset
registration is deferred; a local developer or future CI job can invoke batch
training after approval. There are no background schedulers or automatic retries.

The plan is read-only. Runs store `plan.json` and `result.json` under ignored
`system/.local/training_runs/<run-id>/`; individual candidate bundles are retained
for inspection. Normal completion/failure deletes temporary train/validation
exports, not raw data. A crash can leave exports/partial files, so inspect and
remove interrupted local runs manually. History can identify incomplete runs but
cannot tell whether another process is actively running. Do not run cleanup while
training or collection is active. Error messages are local developer diagnostics;
do not pass secrets as parameters or publish run directories.

## Trainer contract

A trusted implementation implements `TrainingStrategy.run(context)` in
`fingerprinting/training/`. `TrainingContext` carries method, artifact ID,
dataset/split identifiers and SHA-256, eligibility policy, train/validation JSONL
paths, a candidate output directory and method parameters. It must produce a
manifest and all declared files under that directory. The existing onboarding
contract applies: use exact canonical labels, compatible adapter ABI, declared
runtime dependencies, training code revision and source. Preserve raw null/empty
response behavior in training and inference; feature-level representation needs
method-specific review. If a method writes invalid data or raises an exception,
that candidate is not registered. A successful structural check is **not** runtime
validation. Tests use synthetic, non-executable payloads only.

| Method | One-time handoff required | Next integration |
|---|---|---|
| RF | Final preprocessing, ordered features, training script/config, label mapping, sklearn version | Adapt reference code; verify train/inference feature parity and empty response behavior |
| Harness | Reference extraction rules, six-probe coverage, sample policy, judge/model rules | Build references only when relevant data changes; preserve old bundle; no conventional fitting |
| LoRA | Training notebook/script, pinned base revision, serialization, input format, labels, hyperparameters, GPU requirements | Add reproducible local/GPU trainer and checkpoint parity |
| Stage 1 | Supported identities, training design, features, thresholds, environment | Generalize four-ID adapter before expanded training; keep opt-in |

Harness needs special reference-session/split design: the generic prompt-disjoint
split allocates the six fixed probes across partitions, so it cannot directly
produce a complete six-probe reference/evaluation protocol. Do not silently mix
partitions to fix coverage. Threshold calibration remains deferred. Real backend
inference also remains mock-judge Harness until the next integration milestone.

## Tests

```bash
python -B -m unittest discover -s tests/core -t . -p 'test_training_orchestrator.py' -v
python -B -m unittest discover -s tests/core -t . -p 'test_*onboarding.py' -v
```
