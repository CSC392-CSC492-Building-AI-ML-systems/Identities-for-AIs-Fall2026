# Model and family onboarding — local prototype

## Scope and source of truth

A **target identity** is an LLM we want to recognize, not a trained fingerprint classifier. Keep `system/catalog/models.json` authoritative for canonical identity/family metadata, `system/collector/models.yaml` for provider routing, and `cards/` for compliance, governance, evaluation and risk research. The team's `cards/cardlib.py` already derives a family-level card from the known model cards with `confirmed: false`; there is no separate family registry or duplicate family-card directory. The identity submission's family name must normalize to its canonical family ID and agree with existing members' developer and authoritative card labels. This deliberately conservative single-developer family rule can be reviewed manually for joint-development families. Product line is optional and distinct from broad family. New entries retain identity source URL, access and family display metadata in the existing JSON (existing inference catalog reads its established fields). Provider routing does not establish actual model identity. Identity-source URLs are supplied by researchers, never fetched/verified by this CLI.

The tool is offline and expects a trusted local checkout with `system/collector/` and sibling `cards/`; the root release includes both folders. Run on a clean Git branch with no concurrent manual edits. New collector routes are disabled. Registered classifier support is read from existing manifests, not inferred from the catalog, and does not imply readiness, calibration or activation. No model/provider/judge calls, no training, no Stage 1, no new transport or card endpoint. Live target backend currently supports only OpenAI; collector supports Ollama, OpenAI, Anthropic and Google. Additional transports require integration and tests.

## 1. Inspect before changing anything (PowerShell, repository root)

```powershell
python -m pip install -r system/requirements-integrated.txt
python system/run.py onboard-model status
```

The command audits every canonical model's collector route and enabled flag, four domain cards using the existing `check_cards.check_file`, declared Stage 2 artifact support, family membership and collector-only identities. It is read-only. `reports/model_onboarding_snapshot_audit.json` is an audit of the previously uploaded full repository snapshot, **not** a claim about the current checkout. That snapshot has 17 identities, six families, nine matching routes, six missing routes (Claude Haiku 5.5, Gemma 3 1B, GPT-6 Luna, GPT-6.1 Terra, Llama 3.2 1B, Qwen2.5 3B) and two mismatched GPT-5.6 routes containing `TODO-confirm`. All 44 existing cards lack `researched_by`; 24 cards are missing. The values themselves were not fact-checked. Do not invent authors or overwrite conflicting routes automatically.

## 2. Prepare a submission and register

```powershell
Copy-Item system/config/onboarding/model_example.json system/config/onboarding/model_local.json
```

Replace **all** example values (the source placeholder intentionally fails validation). Use exact provider IDs confirmed by the team, official identity documentation and the actual researcher name. Required fields: `model_id`, `family_id`, `family_name`, `developer`, `display_name`, `provider`, `provider_model_id`, `access` (open/closed), `identity_source` (HTTPS), `researched_by`. Optional: `product_line`, integer `delay_seconds`. IDs must be portable lowercase filesystem components. Existing routes, identity fields, and labels cannot be silently changed or duplicated. The submission may be used to backfill a missing collector row for an existing identity if its canonical fields match exactly. For a new identity within an existing family:

```powershell
python system/run.py onboard-model plan config/onboarding/model_local.json
python system/run.py onboard-model register config/onboarding/model_local.json
```

For the first member of a new family:

```powershell
python system/run.py onboard-model plan config/onboarding/model_local.json --allow-new-family
python system/run.py onboard-model register config/onboarding/model_local.json --allow-new-family
```

`run.py` resolves relative CLI paths from `system/`. Registration appends an identity to `catalog/models.json` and a disabled entry to `system/collector/models.yaml`, preserving old entries and YAML comments. It can be repeated without changing matching entries. The existing lock protects concurrent tool writers, checks old bytes before replacement, and attempts rollback on ordinary errors. It is not a transaction across power loss/process termination; use Git diffs to review/recover; stale `.local/model_onboarding.lock` must only be removed after confirming no writer is running. Commit catalog and collector together. Restart the local backend after catalog additions; runtime processes may have cached the catalog.

## 3. Research cards independently

```powershell
python system/run.py onboard-model draft-cards config/onboarding/model_local.json
```

The existing `cards/new_model.py` generates four TODO templates under `system/.local/model_onboarding/<model_id>/<domain>/<model_id>.yaml`, outside the authoritative library. Existing draft work is not overwritten; existing authoritative card files are not copied or replaced. Research each field using actual sources, retrieval dates and evidence levels. Fill the compliance `licence_id` and review the team's `system/collector/licences.yaml`; add a supported licence record or update the correct `applies_to` list with evidence, following the team's existing process. Do not assume a licence from family membership. Review rights to use responses for classifier training as well as collection. Missing disclosure must follow the existing card schema with source, not guessed values.

```powershell
python system/run.py onboard-model publish-cards config/onboarding/model_local.json
python system/run.py onboard-model status
```

Publication checks all four domains (including already present cards), exact identity/family/access headers, the existing checker and an official licence URL. TODOs or structural errors prevent publication. This is an explicit local research publication, not legal, factual or organizational approval. The tool only publishes missing domain files; edits to existing authoritative cards remain a separate reviewed workflow. Historical invalid cards are reported rather than hidden or rewritten. The existing `cardlib` can still return historical incomplete cards; fixing legacy metadata is a separate task.

After publication, the existing card library can derive family-level information (version unknown, not confirmed):

```powershell
python cards/show_card.py --family Example
```

Replace `Example` with the actual family name. There is no separately trained family classifier and no ability to identify arbitrary unknown families merely by registering metadata.

## 4. Collect, onboard and retrain

After independently confirming provider routing, data-transfer/licence permission and credentials, manually set the new collector entry to `enabled: true`. Begin with the team's dry run:

```powershell
python system/collector/collect.py --model YOUR_MODEL_KEY --prompts system/collector/prompts/fingerprinting_prompts.yaml --prompt-set-version fingerprint_v0 --dry-run
```

Use the same probe definitions, personas, sample protocol and comparable settings across existing and new models. For actual collection remove `--dry-run` only after review; this may incur costs. For a fixed-panel expansion, assemble one complete raw collection across intended classes (not just the new model), without duplicating overlapping record IDs or mutating registered raw snapshots. Use a fresh dataset version and approved new split; review overlap with historical references. The existing tools are documented in DATASET_ONBOARDING.md, RF_MULTI_PROMPT.md, HARNESS_REFERENCE_BUILDER.md and LORA_TRAINING.md. Example dataset validation from repository root:

```powershell
python system/tools/onboard_dataset.py validate system/collector/data/raw
```

Then register the approved new snapshot, create a `split-panel` using complete common probes and disjoint persona groups, update the training configs with new dataset/split IDs and unused artifact versions, and use the existing `training plan/run` commands. RF and Harness can run on CPU; LoRA actual training/reload is pending (CPU smoke or GPU). Existing candidate artifacts do not gain the new label until genuinely retrained/refreshed, registered and evaluated. Review-only operation remains in effect. Automatic approval-triggered retraining and publication are not implemented here.

## Validation performed

14 new unit tests + 94 related onboarding, registry, layout, Harness and Stage 2 backend tests passed. In a throwaway copy of the actual sibling card library/collector, registered a synthetic seventh family; confirmed disabled route, draft-only behavior, refusal of unfinished cards, structural publication with synthetic test-only evidence, family aggregate unconfirmed and no Stage 2 artifact support. Existing fixed-panel split remained verifiable after catalog append; one synthetic blank response for the new identity passed dataset validation. Synthetic identity/cards/data were not shipped. No real new model, provider calls or classifier training. Historical complete regression suite not rerun; the first focused backend invocation required the parent repository on PYTHONPATH, then passed. No old artifacts, raw data, backend, production config or authoritative root files changed in the shipped archive.
