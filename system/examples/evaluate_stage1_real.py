"""Evaluate the real Stage 1 classifiers on a prompt-held-out CSV.

Unlike the original binary target-only experiment, this measures the STRICT
family->within-family-model->threshold verdict used by the current pipeline.
The evaluation file is supplied separately and is not included in the package.

Example:
  python examples/evaluate_stage1_real.py --csv path/to/test.csv --limit-per-model 20
  python examples/evaluate_stage1_real.py --csv path/to/test.csv --limit-per-model 0

Each response is paired with every expected model, simulating unchanged and
swapped deployments; ground truth is never passed to the verifier.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import random
import warnings
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fingerprinting.adapters.logistic_regression import build_logistic_regression, MODEL_TO_FAMILY
from fingerprinting.config import Stage1Selection
from fingerprinting.evaluation import EvaluationRunner
from fingerprinting.model_catalog import ModelCatalog
from fingerprinting.registry import ArtifactRegistry
from fingerprinting.schemas import EvaluationCase, FingerprintRequest, Observation


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv', type=Path, required=True)
    p.add_argument('--limit-per-model', type=int, default=20, help='0 = use every row; otherwise use first N per actual model')
    p.add_argument('--output', type=Path, default=ROOT/'reports/stage1_holdout_report.json')
    args = p.parse_args()
    if args.limit_per_model < 0:
        p.error('limit-per-model must be >=0')
    if args.output.resolve() == args.csv.resolve():
        p.error('Output cannot overwrite the input dataset')
    # Prefer different prompt IDs before repeating a prompt's reruns.
    # This avoids an early-row sample representing only a handful of prompts.
    grouped = defaultdict(lambda: defaultdict(list))
    with args.csv.open(newline='', encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            actual = row['model_key']
            if actual in MODEL_TO_FAMILY and row['response_text'].strip():
                grouped[actual][row['prompt_id']].append(row)
    selected = []
    counts = defaultdict(int)
    for model_id in MODEL_TO_FAMILY:
        by_prompt = grouped[model_id]
        prompt_ids_for_model = sorted(by_prompt)
        rng = random.Random(42)
        rng.shuffle(prompt_ids_for_model)
        # For every prompt ID, keep original row order; across prompt IDs,
        # round-robin so sample 0 and sample 1 do not crowd out other prompts.
        max_reps = max((len(by_prompt[k]) for k in prompt_ids_for_model), default=0)
        for rep in range(max_reps):
            for pid in prompt_ids_for_model:
                if args.limit_per_model and counts[model_id] >= args.limit_per_model:
                    break
                rows = by_prompt[pid]
                if rep < len(rows):
                    selected.append(rows[rep])
                    counts[model_id] += 1
            if args.limit_per_model and counts[model_id] >= args.limit_per_model:
                break
    cases = []
    prompt_ids = set()
    for row in selected:
        actual = row['model_key']
        prompt_ids.add(row['prompt_id'])
        for expected in MODEL_TO_FAMILY:
            case_id = f"{row['record_id']}|expected={expected}"
            request = FingerprintRequest(case_id,
                Observation(row['prompt_text'], row['response_text'], row['prompt_id']),
                expected, MODEL_TO_FAMILY[expected])
            cases.append(EvaluationCase(case_id, request, actual, MODEL_TO_FAMILY[actual],
                                        'collector_supervised', row.get('split','test'),
                                        persona_id=row.get('persona_id'), prompt_group_id=row.get('prompt_group'),
                                        source_record_ids=[row['record_id']]))
    if not cases:
        p.error('No matching nonempty responses for the four supported models')
    registry = ArtifactRegistry(ROOT, ModelCatalog.from_file(ROOT/'catalog/models.json'))
    manifest = registry.get('stage1_lr/v1')
    if not registry.readiness('stage1_lr/v1').ready:
        raise RuntimeError('Stage 1 artifact is not ready')
    output = {
        'note': 'Real model inference; prompt-held-out subset of original collector test CSV, not end-to-end Stage 2 accuracy',
        'source_csv_name': args.csv.name,
        'source_sha256': __import__('hashlib').sha256(args.csv.read_bytes()).hexdigest(),
        'sample_counts_per_actual_model': dict(counts),
        'n_unique_response_samples': sum(counts.values()),
        'n_unique_prompts': len(prompt_ids),
        'n_pairs_per_approach': len(cases),
        'n_unchanged_cases_per_approach': sum(c.actual_model_id == c.request.expected_model_id for c in cases),
        'n_swap_cases_per_approach': sum(c.actual_model_id != c.request.expected_model_id for c in cases),
        'manifest_sha256': manifest.manifest_sha256,
        'artifact_id': manifest.artifact_id,
        'methodology': 'Deterministic seeded prompt-diverse sampling (seed=42), then all four expected models paired with each sampled response; predictions use response text only.',
        'limitation': 'Same response reused for four expected model scenarios; observations are correlated. No unknown out-of-set families. Metrics are descriptive, not independent confidence intervals.',
        'results': {},
    }
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for approach in ('hierarchy_hard_route', 'hierarchy_soft', 'ovr_direct'):
            verifier = build_logistic_regression(manifest, Stage1Selection('logistic_regression', manifest.artifact_id, approach))
            report = EvaluationRunner.stage1(cases, verifier)
            output['results'][approach] = report.metrics
            print(f"{approach}: {json.dumps(report.metrics, sort_keys=True)}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2)+'\n', encoding='utf-8')
    print('Saved:', args.output)


if __name__ == '__main__':
    main()
