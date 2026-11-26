# Unified LLM fingerprinting — Integration and Evaluation (November 2026)

## Stage 1 is optional (November 2026 update)

**Default:** `stage1.enabled: false` in `config/production.yaml`. The normal `FingerprintPipeline` runs Stage 2 directly (LoRA → Harness → RF); it **does not load or call Stage 1** unless enabled in YAML or by `pipeline.run(request, use_stage1=True)`.

- Stage 2-only requests can omit `expected_model_id` and `expected_family_id`; an accepted identity returns `final.status: identified`.
- When Stage 1 is requested, both expected IDs are required. Set `stage1.enabled: true` in YAML or pass `use_stage1=True` per call.
- Evaluate the default: `python system/run.py evaluate --rf-pilot --scope e2e --methods random_forest` from the GitHub root.
- Evaluate Stage 1 enabled: append `--use-stage1` to that command. `--scope stage1` still evaluates Stage 1 independently.
- Run the local real-RF demonstration without Stage 1: `python system/run.py example stage2_default_real_demo`.
- Inspect optional Stage 1 readiness: `python system/run.py config --use-stage1`.

**Frontend handoff:** `docs/UI_INTEGRATION.md` — proposed UI behavior and backend API contract.

**Backend handoff:** `docs/BACKEND_INTEGRATION.md` — real Python API plus missing service, security and operational extensions. **No HTTP API is implemented in this package.**

The result contract is now `schema_version: 1.1` (added `identified`, `stage1_enabled`, and `stage1.verdict: skipped`). YAML configuration schema stays `1.0`; older YAML files without `stage1.enabled` default to false.

---


**Repository layout:** Keep this complete directory as `system/` at the **root of your
existing GitHub repository**, alongside your other projects. Do **not** scatter
`fingerprinting/`, `models/`, `tests/`, `TBD.md`, or the other subsystem files into
the repository root. They all live in `system/`.

It extends the versioned Strategy Pattern + Factory pipeline with a single offline
**evaluation command** for Stage 1, independent Stage 2 methods, and the entire
configured pipeline. The production pipeline and its classification behaviour
remain separate from evaluation scoring.

**Start here:** [Unified evaluation guide](docs/UNIFIED_EVALUATION.md) ·
[Open work / missing artifacts](TBD.md) · [Model registry](models/registry.json).

```bash
# All commands here are run from the GitHub repository root:
python -m pip install -r system/requirements-integrated.txt
python system/run.py test
python system/run.py evaluate --rf-pilot --scope all
python system/run.py evaluate --rf-pilot --scope e2e --methods random_forest
python system/run.py config
# Linux / macOS / Git Bash: ./system/run.sh evaluate --rf-pilot --scope all
```

The launcher works regardless of the shell's current directory; relative input
paths and output report directories are interpreted **inside `system/`**. For
example, evaluation reports default to `system/reports/unified_pilot/`, and
pending work is in `system/TBD.md`. You may also `cd system` and use the
original `python -m fingerprinting.eval_cli ...` commands in the historical
sections below. Python code in the wider repository can import
`system.fingerprinting.*` when the repo root is on `PYTHONPATH`.

**Folder placement:** Extract the ZIP into the repository root. The archive's
single top-level directory is `system/`; existing root files remain unchanged.


**Current limitations:** LoRA's trained weights are missing, the Harness judge is
mocked unless explicitly authorized, and LoRA/RF reject automatic acceptance
until unknown-model thresholds have been validated. Thus the **full configured**
LoRA → Harness → Random Forest E2E evaluation is correctly reported as **blocked**.
The Stage 1 → RF subset is a diagnostic, not the complete production pipeline.
All manual follow-ups are tracked in [`TBD.md`](TBD.md).

---

# Stage 2C: Real five-class Random Forest integrated

This is an extension of the previous Stage 1 + LoRA adapter + Harness project.
The **Stage 2C Random Forest identifier now runs on a real fitted 500-tree
classifier**, versioned as `random_forest/v1`. The exact 52-feature contract
and five class labels are preserved. It uses the existing `Stage2Identifier`
Strategy interface and the Pipeline Factory. Prior components are retained.

## Run it

From the extracted project directory (Python 3.10+; the exported forest was
built on scikit-learn 1.8.0):

```bash
python -m pip install -r requirements-integrated.txt
python -m unittest discover -s tests -v
python -m fingerprinting.config_cli config/experiments/random_forest_only.yaml --root . --require-ready
python examples/random_forest_real_demo.py
python examples/evaluate_random_forest_real.py
python examples/stage1_random_forest_demo.py
```

These commands do **not** make network/API requests. To run standalone RF:

```python
from fingerprinting.adapters.builders import real_adapter_constructors
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import PipelineFactory

config = load_pipeline_config('config/experiments/random_forest_only.yaml', registry)
stage2 = PipelineFactory(registry, real_adapter_constructors()).build_stage2(config)
run = stage2.execute(context)  # IdentificationInput with initial Observation
```

The same `real_adapter_constructors()` registers all four implementations for
full pipeline construction; the complete production config cannot pass
readiness until the LoRA adapter weights are provided. Stage 1+RF alone can
run end-to-end today using `config/experiments/random_forest_only.yaml`.

## Original implementation and export

The source repository supplied `train_fingerprint_rf.py`,
`prepare_fingerprint_rf.py`, 2,933 prepared all-persona training rows and the
132-row P13 test set, but did **not** supply the fitted five-class forest.
The fitted file in `models/random_forest/v1/classifier.joblib` was **retrained
from those existing feature tables**, not copied from an original model export.
Training settings: 500 trees, class_weight=balanced, random_state=42,
SimpleImputer(strategy='median'). Use `tools/export_random_forest.py` with the
original `collector/data/ml_ready` folder to reproduce a new export. Training
is not part of the runtime interface.

**Saved original evaluation:** 124/132 correct (93.94%).
**New reconstruction under scikit-learn 1.8.0:** 123/132 correct (93.18%).
The re-export agreed on 129/132 stored predictions. These are historical
**fixed-prompt, response-held-out** results, not estimates on unseen prompts,
unseen model families, or a new application environment. The classifier uses
prompt-ID one-hot columns, output tokens and latency, so a change of serving
environment may materially change accuracy. See
`reports/random_forest_export_validation.json` and
`reports/random_forest_independent.json`.

## Inference feature and acceptance contract

- Original 52 predictor columns are provided in
  `models/random_forest/v1/feature_manifest.json`; class ordering is pinned in
  `models/random_forest/v1/manifest.json`.
- Runtime features are generated from **the initial response and its prompt**,
  with optional output tokens and latency, never expected or true model IDs.
- Line endings are normalized from CRLF/CR to LF before feature extraction.
  This reconciles the processed source CSV with the saved training feature
  counts. The feature extractor itself is bundled byte-identically in the
  adapter and versioned artifact; future feature contracts need an explicit
  adapter compatibility update.
- Missing backend measurements retain missing-value flags and the imputer
  handles their null values. Unknown prompt IDs activate no known prompt-ID
  one-hot column. Both situations are flagged in diagnostics as potential
  distribution shift.
- The forest is **closed-set**. The default acceptance policy is
  `review_only`: a proposed model ID and per-class scores are returned, but
  `accepted_model_id=None`, `handoff_requested=True`, and final outcome is
  `needs_review` if no earlier method identified a model. This is intentional;
  no unknown-model rejection threshold has yet been validated.
- An optional `validated_threshold` mode is interface-tested with synthetic
  scores, but it MUST NOT be enabled in production without separately held-out
  unknown-model and deployment-shift validation.

## What is working vs. pending

| Component | State |
|---|---|
| Stage 1 LR | Real saved models load and verify inputs |
| Stage 2A LoRA | Adapter implemented; trained PEFT weights missing |
| Stage 2B Harness | Versioned reference bundle and offline mock judge tests pass; live judge not tested |
| Stage 2C RF | **Real 500-tree model integrated, checksummed and evaluated** |
| Independent RF evaluation | 132 cases, 93.18% top-1 candidate accuracy, 0 accepted by conservative policy |
| Real Stage 1 -> RF | End-to-end smoke run passes (other Stage 2 methods excluded) |
| Full LoRA -> Harness -> RF chain | Strategy routing mock-tested; real chain still blocked by missing LoRA weights and live judge verification |

### Environment caveat for full process

Stage 1 Logistic Regression files were serialized with **scikit-learn 1.6.1**.
The refitted RF was exported under **scikit-learn 1.8.0**. The provided
`requirements-integrated.txt` installs 1.8.0, and Stage 1 parity/smoke tests
ran here despite scikit-learn cross-version unpickling warnings. That does
**not** guarantee safe production compatibility. Before deployment, either
re-export all sklearn artifacts under one validated environment, or serve
versions in separate, pinned worker processes. Do not pip-install both
`requirements-stage1.txt` and `requirements-random-forest.txt` together as they
pin incompatible scikit-learn versions. Never deserialize untrusted joblib
artifacts.

To provide the missing LoRA weights, place
`adapter_model.safetensors` and `adapter_config.json` in `models/lora/v1/`
and use the existing installer to update checksums and pin the base revision.

---

# LLM Fingerprinting — Stage 2B: AI Harness Integrated

This is an **incremental extension** of the earlier Strategy Pattern pipeline. Existing
`Stage1Strategy`, `Stage2Identifier`, `Stage2Strategy`, `FingerprintPipeline`, and
`EvaluationRunner` are retained. The new code **loads real Stage 1 weights only when the real Stage 1 builder is explicitly used**,
**does not train any model**. The Harness can make an external judge API request only when invoked with a non-mock judge provider.

**Current status:** Stage 1 LR is real and tested; Stage 2A LoRA adapter is implemented but awaits weights; Stage 2B Harness is bundled and executes its original six-probe logic, references, rules and card lookup; Stage 2C Random Forest is pending. The full configured production pipeline is not yet runnable.

## Quick start

Requires Python 3.10+ and PyYAML 6.x.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m fingerprinting.config_cli config/production.yaml --root .
python -m fingerprinting.config_cli config/evaluation.yaml --root .
python -m fingerprinting.config_cli config/experiments/lora_only.yaml --root .
# Construct a running pipeline from YAML using MOCK classifiers (no model files required):
python examples/factory_demo.py
python examples/factory_demo.py config/experiments/lora_only.yaml
python examples/factory_demo.py config/evaluation.yaml
```

Each `config_cli` call checks that the **selection is valid** and prints a
config digest, per-version manifest digests, and an **artifact readiness report**.
Stage 1 `stage1_lr/v1` and Stage 2B `harness/v1` are **artifact-ready**, with
checksummed files. LoRA and Random Forest are still missing trained inference
artifacts, so **full production** readiness is false. Harness artifact readiness
does not imply judge-API credentials or network access are available.

To require both a valid configuration and present, checksummed artifacts:

```bash
python -m fingerprinting.config_cli config/production.yaml --root . --require-ready
```

This last command is **expected to fail** because LoRA and Random Forest files are still
missing, although Stage 1 and Harness are ready. The CLI never loads or deserializes `.joblib`.


## Stage 2B Harness — current release

The Harness is an **exact-model** identifier in Stage 2, not an independent family
classifier. It sends six fixed probes through `TargetClient`, then reuses the
original `identify_api.py` → `check_chatbot.py` → `probe_identify.py` and
`card_lookup.py` code. Stage 1 alone verifies family and expected model.

### Key files

| File | Purpose |
|---|---|
| `fingerprinting/adapters/harness.py` | Strategy adapter; converts the original Harness status, fit and handoff fields to `IdentificationResult` |
| `fingerprinting/adapters/harness_worker.py` | Runs the legacy Harness in its own Python interpreter; avoids import conflicts when version-swapping |
| `models/harness/v1/` | Checksummed Harness source, the six original probes, collector sample **0/1** references and cards |
| `fingerprinting/clients.py` | Adapter for a backend's `send_prompt(str) -> str` callback |
| `testdata/harness_replay/` | Example **sample-2** replay answers, kept outside the inference artifact to prevent training/test leakage |
| `config/experiments/harness_only.yaml` | Evaluate just Stage 2 Harness, without LoRA or RF |
| `config/experiments/stage1_harness.yaml` | Real Stage 1 + Harness-only E2E smoke test |
| `tests/test_harness_adapter.py` | Adapter, routing, replay, Factory, acceptance and card integration tests |
| `tests/test_harness_upstream_rules.py` | Executes all 18 original Harness rules tests from the correctly bundled source directory |

### Run it (offline: no API charges)

```bash
python -m pip install -r requirements-stage1.txt
python -m pip install -r requirements-harness.txt
python -m fingerprinting.config_cli config/experiments/harness_only.yaml --root . --require-ready
python -m unittest discover -s tests -v
python examples/harness_real_demo.py --judge-provider mock
python examples/stage1_harness_demo.py
```

The first demo runs the **real original Harness** (references, deterministic
rules, cards) with a *mock LLM judge*. It cannot establish an accepted identity
or meaningful accuracy. The E2E demo runs **real Stage 1 + Harness with mocked
judge** and demonstrates fallback and probe collection, not model-ID accuracy.

To call the real judge, supply `GEMINI_API_KEY` through the environment and run:

```bash
python examples/harness_real_demo.py --judge-provider google
```

This invokes an external API and may incur cost. Actual judge accuracy and
end-to-end accuracy have **not** been measured in this release. The original
Harness source includes its own set of model IDs and rule thresholds. We have
preserved these rather than silently modifying its decisions.

**Acceptance rules:** The adapter only accepts an exact supported `model_key`
when the original Harness says `Identified` or `Verified` **and** does not
request handoff; `mock` judge results can never be accepted. A returned
`closest_known_version` is diagnostic evidence, not a confirmed model ID.
Family/developer detail and the selected domain card remain available as
**diagnostics**, not as separate Stage 2 predictions. The shared pipeline
still reports `needs_review` if no method accepts an exact model.

The worker checks out-of-process source from the selected `harness/vN` artifact,
so different versions can have distinct probes and references. Each bundle's
files have SHA-256 hashes in `manifest.json`. A new version should go into a
new folder, with its own reference snapshot and manifest, **not overwrite v1**.

### Live target chatbot and registered deployments

Stage 2 asks the selected target client only when it needs probes:

```python
from fingerprinting.clients import CallableTargetClient
client = CallableTargetClient(send_prompt=my_chatbot_api_call)
result = pipeline.run(request, target_client=client)
```

Implement `my_chatbot_api_call(prompt: str) -> str` in your backend. No provider
client or credentials are hardcoded into the fingerprinting system. Offline
runs use `ReplayTargetClient` instead. `target_client` and judge provider are
**different** connections: one queries the unknown model, the other asks the
judge to identify that model.

To use the Harness's **registered-baseline** mode, provide the original
registration JSON and pass `deployment_id` in the request. Set an external
`FINGERPRINTING_DEPLOYMENTS_DIR` directory containing `<deployment_id>.json`
for the Harness subprocess to read. Do **not** store mutable registered
baselines in the immutable `models/harness/v1` snapshot.

### Where to install the missing LoRA weights

**Upload `my_lora_adapter.zip` in this chat when it becomes available**, or
place the archive anywhere locally and run:

```bash
python tools/install_lora_adapter.py /path/to/my_lora_adapter.zip \
  --base-revision <full-40-character-Qwen-base-model-commit>
```

The installer validates and places the files at:

```text
models/lora/v1/adapter_model.safetensors
models/lora/v1/adapter_config.json
```

The saved adapter must contain its trained sequence classification head. The
training team also needs to provide the **exact base-model commit**; the
installer requires that for reproducible inference. Do not just drop an
unvalidated adapter into production or overwrite an already released version.

### Known limitations

- The real judge call requires configured API credentials/network and has not
  been tested here.
- No external target-LLM API has been queried; live probe-collection integration
  depends on your backend's `CallableTargetClient` callback.
- The Harness's original `mock` judge makes random guesses; its outputs are
  useful only for plumbing and rules/card smoke tests.
- `harness/v1` currently snapshots reference responses **sample 0 and 1** for
  the six probes. Test sample 2 is outside the artifact. This checks file-level
  separation, but does not establish independent-prompt generalization.
- A few original reference sets, particularly Qwen3.5, have sparse probe data.
  We preserve the original fallback/check rules but have not calibrated their
  real-world error rates.
- The full production fallback `LoRA → Harness → RF` still fails readiness
  until missing LoRA weights and the trained RF bundle are installed.

## Responsibilities and design decisions

| Component | File | Responsibility |
|---|---|---|
| Canonical model catalog | `catalog/models.json`, `fingerprinting/model_catalog.py` | Resolve stable **target LLM** model IDs to family/developer/product line. Does not contain classifier versions. |
| Inference artifact registry | `models/registry.json`, `models/*/v*/manifest.json`, `fingerprinting/registry.py` | Record **fingerprinting classifier** versions and their capabilities, required files and provenance. |
| Pipeline config | `config/*.yaml`, `fingerprinting/config.py` | Select one Stage 1 artifact/approach and an ordered list of Stage 2 artifacts/mode. |
| Configuration inspector | `fingerprinting/config_cli.py` | Validate selection and check artifact presence/integrity, without executing models. |
| Adapter constructor registry + Pipeline Factory | `fingerprinting/factory.py` | Validate readiness, call registered adapter builders, preserve selected Stage 2 order, and build a running `FingerprintPipeline`. |
| Mock Factory demonstration | `examples/factory_demo.py` | Construct and evaluate configured pipelines with stub classifiers only; outputs are **not actual accuracy results**. |
| Strategy Pattern runtime | `fingerprinting/interfaces.py`, `strategies.py`, `pipeline.py` | Existing strategy routing; the pipeline now also carries artifact provenance. |
| Evaluation runner | `fingerprinting/evaluation.py` | Existing individual/E2E evaluation; now usable with real Stage 1 alone and mock Stage 2 in integration smoke tests. |

### Two kinds of versioning

- **Target model identity:** e.g., `llama3.1-8b` — the identity of the LLM whose text is analyzed.
- **Classifier artifact:** e.g., `lora/v1` — the version of an inference method used to identify it.

They are not interchangeable. Canonical IDs in the model catalog are copied from
`collector/models.yaml` in the supplied `collector.zip`. `family_id` is broad:
`gemini` groups both `gemini-3.1-pro` and `gemini-3.8-flash` for the Stage 1
verification task. `product_line` preserves the Harness's finer `Gemini Pro` /
`Gemini Flash` distinction. The catalog is a snapshot, not a claim of universal
classifier support. Each artifact manifest declares its own supported model IDs.

### Configuration format

```yaml
schema_version: '1.0'
pipeline:
  name: fingerprinting_default
stage1:
  adapter: logistic_regression
  artifact: stage1_lr/v1
  approach: hierarchy_hard_route
stage2:
  mode: fallback
  methods:
    - {adapter: lora, artifact: lora/v1}
    - {adapter: harness, artifact: harness/v1}
    - {adapter: random_forest, artifact: random_forest/v1}
cards:
  enabled: false
```

`stage2.mode` is `single`, `fallback`, or `run_all`; method order is preserved.
`single` must contain exactly one method. Only one instance of a given Stage 2
adapter can appear in a single configured strategy, matching the current strategy
interfaces. Stage 1 supports `hierarchy_hard_route`, `hierarchy_soft`, and
`ovr_direct` in this artifact version.

`cards.enabled` requires a `CardResolver` to be injected into `PipelineFactory`.
No real model-card resolver is bundled yet. With `enabled: false`, card lookup
is not attempted.

### Immutability and reproducibility

Keep a published `models/<algorithm>/<version>/` directory **immutable**. For a
new version, create a *new* directory with a new manifest and update the index.
The registry does not automatically prohibit replacing old files on disk; it
supplies hashes so we can detect differences. `config_sha256` is a canonical
hash of the *selection*. `manifest_sha256` is a separate hash of each version
manifest. Both should be copied into future evaluation reports. The Factory populates `PipelineResult.config_sha256`, `artifact_ids`, and
`manifest_sha256`, which also flow into end-to-end evaluation reports, so runs
can be traced to the selected artifact versions.

A manifest's `required_files` contains paths relative to its own directory.
Set each `sha256` to the **real SHA-256 hash of the actual released file**. An
artifact is ready only when all required files exist **and** all hashes match.
Missing files, missing hashes and mismatches are reported separately.

### Placeholder artifacts and outstanding dependencies

- `stage1_lr/v1`: 7 actual user-supplied `.joblib` classifiers and 12 threshold JSON files are now staged and SHA-256 checksummed. `ArtifactRegistry.readiness("stage1_lr/v1")` is true. Do **not** deserialize third-party/untrusted `.joblib` files.
- `lora/v1`: PEFT adapter (`adapter_model.safetensors`, `adapter_config.json`) still needs to be supplied.
- `harness/v1`: original entry points, six probes, sample-0/1 reference records, cards, and upstream rule tests are now bundled and checksummed. Runtime still needs judge API credentials for real identification.
- `random_forest/v1`: trained five-class forest plus the exact feature manifest/extractor have not yet been exported as a compatible inference bundle.

Stage 1 and Harness now have complete checksummed artifact snapshots. The LoRA
and Random Forest manifests remain initial *declarations*, not proof of a
reproducible release. Harness readiness checks local files, not remote judge
API access; LoRA and RF still need weights and runtime validation.

### Switching versions without changing pipeline code

1. Train or assemble the new artifact in a **new** version directory, e.g. `models/lora/v2/`.
2. Produce a manifest with `artifact_id: lora/v2`, supported model IDs, labels/feature contracts, required files **and their checksums**, training provenance and compatible adapter.
3. Add `"lora/v2": "models/lora/v2/manifest.json"` to `models/registry.json`.
4. Change only `artifact: lora/v1` to `artifact: lora/v2` in the selected YAML; validate readiness, then run frozen individual and E2E evaluations before promotion.

Version selection **and automatic construction of configured strategies** are now
implemented and mock-tested. The actual classifier builders still need to be
registered before the pipeline can use real models.

### Validation boundaries

- Reject unknown artifact versions, invalid strategy names, wrong stage/adapter
  assignments, duplicate YAML keys, duplicate Stage 2 methods, and unsupported
  Stage 1 approaches.
- Reject model IDs not in the catalog and unsafe paths (`..`, absolute paths,
  symlink escapes) during manifest validation.
- YAML parsing uses PyYAML's safe loader; API secrets are not written to YAML.
- `readiness` checks bytes without loading executables, model pickles or packages.
- Ground truth stays exclusively in `EvaluationCase`; no inference API accepts it.

## Pipeline Factory: construction and integration

`PipelineFactory` is the **composition root**, not the evaluation runner.
It creates the chosen strategies once, and `FingerprintPipeline.run()` performs
runtime routing. `EvaluationRunner` measures the output independently. A
constructor registry maps known adapter names to trusted, explicit Python
functions; YAML never contains executable import paths.

```python
from pathlib import Path
from fingerprinting.config import load_pipeline_config
from fingerprinting.factory import AdapterConstructors, PipelineFactory
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry

root = Path.cwd()
catalog = ModelCatalog.from_file(root / "catalog/models.json")
registry = ArtifactRegistry(root, catalog)
config = load_pipeline_config(root / "config/production.yaml", registry)
constructors = AdapterConstructors()

# These constructors must be implemented in the REAL adapter milestone.
# They accept a version manifest and a validated selection.
constructors.register_stage1("logistic_regression", build_logistic_regression)
constructors.register_stage2("lora", build_lora)
constructors.register_stage2("harness", build_harness)
constructors.register_stage2("random_forest", build_random_forest)

factory = PipelineFactory(registry, constructors)  # require_ready=True by default
pipeline = factory.build(config)
result = pipeline.run(request, target_client=live_client)
```

The example above documents **future real-builder wiring**: functions named
`build_logistic_regression`, `build_lora`, `build_harness`, and `build_random_forest`
do not exist in this package yet. For a working runnable example with stub
constructors, run `python examples/factory_demo.py`.

Factory behaviour:

1. Verify the `PipelineConfig` digest and all artifact IDs, stages, approaches,
   and version manifests; reject a manifest changed after registry caching.
2. Check that all required constructor functions are registered **before**
   initializing models.
3. In default mode, require every selected artifact to be present and SHA-256
   checked. Missing, mismatched, and unchecksummed bundles **fail** early.
4. Invoke one Stage 1 constructor and each ordered Stage 2 constructor with
   its manifest. Builders can load/cache models or defer costly loading.
5. Create `SingleMethodStrategy`, `FallbackStrategy`, or `RunAllStrategy` from
   the YAML selection, and return a `FingerprintPipeline`.
6. Preserve provenance in `PipelineResult`: config digest, artifact IDs, and
   each selected manifest's SHA-256. E2E reports also retain this provenance.

`PipelineFactory(..., require_ready=False)` is intentionally available only for
**mock/isolated tests** with `StubStage1` / `StubIdentifier` and metadata-only
manifests. It must not be used to bypass missing weights for real inference.
The factory does not deserialize weights or make API requests by itself.

### Individual and E2E evaluation with one built pipeline

```python
from fingerprinting.evaluation import EvaluationRunner

# `cases` contains ground truth, kept out of the runtime inference request.
report1 = EvaluationRunner.stage1(cases, pipeline.stage1)
report2 = EvaluationRunner.stage2(cases, pipeline.stage2)
report_all = EvaluationRunner.e2e(cases, pipeline)
```

To evaluate a single method, use one of the configurations under
`config/experiments/`. To compare all three Stage 2 methods using the same
configured order, choose `config/evaluation.yaml`. The difference is in the
configuration, not in separate pipeline implementations.

**Important:** The Stage 2 standalone report currently contains method-level
metrics but not the Factory's provenance, because it accepts a bare strategy.
E2E reports have full Factory provenance. Propagating factory metadata into
standalone experiment reports belongs in the forthcoming unified evaluation
reporting milestone.

## Testing and current state

```bash
python -m unittest discover -s tests -v
python examples/factory_demo.py
```

Tests cover version switches, strategy switching, expected short-circuiting,
invalid adapter contracts, card-resolver injection, readiness checks, source
manifest changes, early constructor failures, recorded provenance, and existing
individual/E2E evaluation. The original Strategy/Factory tests rely on synthetic stubs; the added real
Stage 1 tests and held-out report explicitly use the trained classifiers.

### Next milestone

Stage 1 Logistic Regression is now integrated; connect Stage 2 in order: LoRA, Harness, Random Forest. Dataset onboarding and retraining remain separate later tasks.


## Real Stage 1 Logistic Regression adapter — integrated

The actual user-provided pretrained Stage 1 classifiers and saved thresholds are
packaged under `models/stage1_lr/v1/` (7 `.joblib`, 12 threshold JSON). All 19
have SHA-256 hashes in the version manifest. The real adapter lives in
`fingerprinting/adapters/logistic_regression.py` and implements
`Stage1Strategy.verify(FingerprintRequest) -> Stage1Result`. It loads the trusted
models once per strategy instance, and preserves the original numerical
`binary_target_score` and `validation_threshold` for all three approaches.

### Run it

A dedicated requirements file is provided:

```bash
python -m pip install -r requirements-stage1.txt
python -m unittest discover -s tests -v
python examples/stage1_real_demo.py --expected-model gemini-3.8-flash \
  --approach hierarchy_hard_route \
  --response-text 'I am Gemini, a large language model developed by Google.'
python examples/stage1_real_demo.py --expected-model llama3.1-8b \
  --approach hierarchy_soft --response-text 'I am a helpful assistant.'
```

For **independent Stage 1 evaluation**, without requiring the missing LoRA or
Random Forest weights, the real Factory supports:

```python
from fingerprinting.adapters.logistic_regression import build_logistic_regression
from fingerprinting.factory import AdapterConstructors, PipelineFactory

builders = AdapterConstructors()
builders.register_stage1('logistic_regression', build_logistic_regression)
stage1 = PipelineFactory(registry, builders).build_stage1(config)
report = EvaluationRunner.stage1(cases, stage1)
```

`PipelineFactory.build(config)` still correctly checks the completeness of
all selected Stage 2 resources, and will **not** construct a production E2E
pipeline with missing weights. The real Stage 1 can also be run inside
`FingerprintPipeline` alongside deliberately mocked Stage 2 strategies for
routing smoke tests.

### Difference between original experiment and production Stage 1 decision

The original experiment's `predicted_target` is a calibrated-on-validation
**binary target consistency** decision: it may accept a model even when its
within-family classifier prefers the sibling, or when `hierarchy_soft` /
`ovr_direct` scores pass with an incorrect hard family route.

The unified Stage 1 contract instead requires **both checks to pass**:
1. A hard family route (`family_score_gemini >= 0.5`) equals the expected family.
2. The within-family model chosen at threshold `0.5` equals the expected model,
   **and** the approach-specific saved target score meets its saved threshold.

When family verification fails, model verification is recorded as *not
attempted* (`model_match=None`, `predicted_model_id=None`). Every real result
includes `scores.original_predicted_target` to compare with original binary
experiment decisions, and preserves the untouched threshold for research
comparisons. Thus score-equivalence does **not** imply the final verification
verdict is necessarily equal to the original experiment's `predicted_target`.
These distinctions are intentional and should be reported when comparing
papers, prior experiments, and E2E accuracy.

The LR models were serialized from **scikit-learn 1.6.1**. The integration parity
suite was run here with **scikit-learn 1.8.0** and matched all original-script
scores on the test fixture texts; nevertheless, scikit-learn does not guarantee
pickle compatibility across releases. Use a controlled Python environment with
`scikit-learn==1.6.1` for reproducible deployment, or re-export compatible
artifacts after independent equivalence testing. As with any pickle, only load
trusted, checksum-verified `.joblib` artifacts.

### Held-out response evaluation

The optional script consumes an existing original collector CSV (not shipped
in this ZIP):

```bash
python examples/evaluate_stage1_real.py \
  --csv /path/to/collector/data/supervised/views/all_personas/test.csv \
  --limit-per-model 20
# For all held-out rows (may require several minutes):
python examples/evaluate_stage1_real.py --csv /path/to/test.csv --limit-per-model 0
```

`reports/stage1_holdout_sample.json` is a completed real-inference evaluation
using the supplied test CSV: 20 prompt-diverse responses per actual model
(80 total across 20 distinct held-out prompt IDs), each paired with all four
expected models (320 verify scenarios per approach), using all three approaches. This is a **small exploratory subset**, not a full
540-response report or a confidence interval. Responses are reused across
simulated expected models, so the evaluation rows are correlated. The subset
supports only the four known Gemini/Llama models and does not test unseen
families. The larger 540-response evaluation was attempted but did not complete
within the execution limit. The report contains methodology and artifact hash.

`reference_stage1/scripts/` is a reference-only copy of the teammate's original
scripts, kept solely to independently test numerical prediction equivalence;
the production adapter does **not** import those training or experimentation
modules.

**C1 migration note (Nov 22, 2026):** The reference copy described above was
removed with approval after verifying all 17 files matched the root research
scripts byte-for-byte. Current parity tests use the repository-root `scripts/`
directory when available, skipping only that original-source parity test in
standalone `system/` distributions. The runtime Stage 1 adapter still uses its
own checksummed trained artifacts. Historical `stage1_lr/v1` manifest provenance
was deliberately not edited; its `source_script` records the original release
location, not a live path. See `docs/CLEANUP_C1_MIGRATION.md`.

---

## Stage 2A integration: LoRA (this release)

This release extends the Stage 1-integrated project with a **real PEFT/Hugging Face
LoRA inference adapter implementation** and the Stage 2-only Factory construction
method. It does **not** include LoRA model weights, produce real LoRA predictions,
or claim measured LoRA accuracy. The LoRA README and notebook provided by the team
specify a Qwen/Qwen2.5-1.5B sequence classifier with 5 exact-model labels and
512-token truncation; we preserve those options in `models/lora/v1/manifest.json`.

### Files added / changed

| Path | What it does |
|---|---|
| `fingerprinting/adapters/lora.py` | Stage2Identifier adapter, lazy HF/PEFT model loading, class-score mapping, validation, explicit handoff policy |
| `fingerprinting/factory.py` | New `build_stage2(config)` independent strategy builder; no Stage 1 weights needed to evaluate one identifier |
| `fingerprinting/evaluation.py` | Method-level **candidate top-1 accuracy** separate from accepted accuracy (critical for review-only policies) |
| `models/lora/v1/manifest.json` | Explicit `review_only` policy; `base_model_revision` placeholder until provided |
| `requirements-lora.txt` | Optional runtime dependencies for real inference; no GPU/Internet use during unit tests |
| `tests/test_lora_adapter.py` | Tests for labels, scores, policy, fallbacks, Factory, evaluator and real Stage 1 routing |
| `tools/install_lora_adapter.py` | Strict manual installer for supplied PEFT ZIP, hashes, and base-model commit; does not train |
| `examples/lora_integration_demo.py` | End-to-end interface demonstration using synthetic LoRA probability scores |
| `examples/lora_real_demo.py` | Real entry point (fails readiness until the PEFT weights are supplied) |

### Why LoRA hands off by default

LoRA is a *closed-set* five-class classifier. It assigns a score to one of its
five known models even when the response comes from an entirely different
model. The current `review_only` policy returns `candidate_model_id`,
`model_scores`, `max_softmax`, and `outcome='unknown'`, then requests handoff
to the AI Harness. This avoids treating uncalibrated softmax as proof of model
identity. An optional `validated_threshold` policy exists, but requires an
explicit validation ID and unknown-model evaluation evidence. It must only be
used after the corresponding real-model acceptance study is complete.

The Stage 2 evaluation runner now records **candidate top-1 accuracy on all
attempted cases**, even when the identifier does not accept an answer. Other
accepted/coverage metrics are unchanged. Offline evaluation still requires a
proper held-out dataset that avoids prompt leakage from the LoRA training run.

### Try the working integration without the missing LoRA weights

```bash
python -m unittest discover -s tests -v
python examples/lora_integration_demo.py
python -m fingerprinting.config_cli config/experiments/lora_only.yaml --root .
```

The demo uses **synthetic** class scores; it does not measure LoRA's accuracy.
The readiness CLI must report LoRA as not ready until weights are available.

### After obtaining the trained PEFT adapter ZIP

The notebook saves `my_lora_adapter.zip` containing `adapter_model.safetensors`
and `adapter_config.json`. Confirm that its safetensors also include the trained
sequence-classification `score` head; without this the output head might be
randomly initialized and predictions would be invalid. Pin the exact 40-character
Hugging Face **Git commit SHA** of the base model used for this release; a bare
model name or branch alias is insufficient for a reproducible release.

```bash
python -m pip install -r requirements-lora.txt
python tools/install_lora_adapter.py /path/to/my_lora_adapter.zip \
  --base-revision <40-character-base-model-commit>
python -m fingerprinting.config_cli config/experiments/lora_only.yaml \
  --root . --require-ready
python examples/lora_real_demo.py --response-text 'A sample response to identify.'
```

The installer validates the two files, safetensors head, model type and base
model, then writes SHA-256 checksums and the pinned revision in the v1 manifest.
**Do not run it over an existing released artifact.** For future retraining,
create `lora/v2` and register it instead of overwriting v1.

A real classifier load requires a compatible runtime with enough CPU/GPU memory,
PyTorch, Transformers, PEFT and the cached/downloadable Hugging Face base model.
The supplied environment did not include Transformers/PEFT, and the user did not
provide the trained weights, so model inference could not be verified here.

### Construction interfaces

```python
constructors.register_stage2('lora', build_lora)
strategy = PipelineFactory(registry, constructors).build_stage2(config)
# OR factory.build(config) once all selected Stage 2 method bundles are ready.
```

The Factory validates only the selected Stage 2 artifacts for
`build_stage2(config)`, making isolated LoRA testing possible before Harness and
Random Forest integration. The production `build(config)` remains strict about
*every* selected artifact being ready.

### Remaining work for LoRA

1. Obtain the actual trained adapter files and pin the base checkpoint revision.
2. Run trained-model predictions and compare them with notebook `which_model()`
   on identical response texts and tokenization settings.
3. Evaluate an unseen-prompt test split, unsupported models, and score-based
   rejection so a validated acceptance policy can be selected.
4. Compare single-response performance to optional multi-response aggregation
   in a separate experiment; this adapter preserves the original single-response
   inference behaviour.

Stage 2B AI Harness is now integrated; Stage 2C Random Forest is the next adapter milestone.
