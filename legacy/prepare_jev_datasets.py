#!/usr/bin/env python3
"""Prepare reproducible Jev one-vs-rest fingerprinting datasets.

Input layout:
    collector/data/raw/<model-directory>/training_v1.jsonl
    training_prompts.csv  (prompt table; may have a title row)

All split assignments are at PROMPT level (shared between all models).
Outputs are experiment-ready CSV/JSON/JSONL files. No Jev API calls are made.

Example:
    python prepare_jev_datasets.py \
        --raw-dir ./collector/data/raw \
        --prompts ./training_prompts.csv \
        --out ./collector/data/jev \
        --personas P13 \
        --reference-sizes 4 8 20 \
        --seed 42
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import sys

SPLIT_NAMES = ("development", "validation", "test")
VIEW_ALL = "all_personas"


def safe_slug(text: str) -> str:
    result = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("._-")
    return result or "unknown"


def stable_seed(seed: int, *parts: object) -> int:
    value = "\u241f".join([str(seed)] + [str(p) for p in parts])
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(row[k], ensure_ascii=False) if isinstance(row.get(k), (list, dict)) else (row.get(k) if row.get(k) is not None else "") for k in columns})


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_prompts(path: Path) -> dict[str, dict]:
    """Find true header, even when a spreadsheet export has a title/banner row."""
    if not path.is_file():
        raise ValueError(f"Prompt metadata file does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headings = None
        prompts = {}
        for idx, items in enumerate(reader, 1):
            if headings is None:
                lowered = {x.strip().lower() for x in items}
                if "source_id" in lowered and "text" in lowered:
                    headings = [x.strip() for x in items]
                elif idx >= 20:
                    raise ValueError("Could not find CSV header containing source_id and text in first 20 rows.")
                continue
            if not any(v.strip() for v in items):
                continue
            row = dict(zip(headings, items))
            prompt_id = row.get("source_id", "").strip()
            if not prompt_id:
                raise ValueError(f"Missing source_id in {path}, CSV row {idx}.")
            if prompt_id in prompts:
                raise ValueError(f"Duplicate source_id in prompt CSV: {prompt_id}")
            if not row.get("text", "").strip():
                raise ValueError(f"Empty prompt text for {prompt_id}")
            prompts[prompt_id] = row
        if headings is None:
            raise ValueError("Could not locate a prompt CSV header.")
    return prompts


def load_responses(raw_dir: Path, prompt_lookup: dict[str, dict], file_name: str) -> tuple[list[dict], dict]:
    sources = sorted(raw_dir.glob(f"*/{file_name}"))
    if not sources:
        raise ValueError(f"No files matching {raw_dir}/*/{file_name}")
    results: list[dict] = []
    counts = Counter()
    seen_record_ids = set()
    model_folders: dict[str, set[str]] = defaultdict(set)
    missed_prompt_ids = set()
    metadata_disagreements = Counter()
    for source in sources:
        with source.open("r", encoding="utf-8-sig") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in {source}:{line_num}: {e}") from e
                if not isinstance(rec, dict):
                    raise ValueError(f"Expected JSON object in {source}:{line_num}")
                counts["loaded"] += 1
                prompt_id = str(rec.get("prompt_id") or "").strip()
                model = str(rec.get("model_key") or source.parent.name).strip()
                if not prompt_id or not model:
                    raise ValueError(f"Missing prompt_id or model_key in {source}:{line_num}")
                if prompt_id not in prompt_lookup:
                    missed_prompt_ids.add(prompt_id)
                    continue
                if rec.get("error") not in (None, "", False):
                    counts["skipped_errors"] += 1
                    continue
                if not isinstance(rec.get("response_text"), str) or not rec["response_text"].strip():
                    counts["skipped_empty_responses"] += 1
                    continue
                record_id = str(rec.get("record_id") or f"{model}:{prompt_id}:{rec.get('persona_id','')}:{rec.get('sample_index', '')}")
                record_identity = (model, record_id)
                if record_identity in seen_record_ids:
                    counts["duplicate_record_ids"] += 1
                    continue
                seen_record_ids.add(record_identity)
                meta = prompt_lookup[prompt_id]
                for left, right in (("prompt_category", "category"), ("persona_id", "persona_id"), ("prompt_group", "group")):
                    if rec.get(left) and meta.get(right) and rec[left] != meta[right]:
                        metadata_disagreements[left] += 1
                out = dict(rec)
                out.update({
                    "record_id": record_id,
                    "prompt_id": prompt_id,
                    "model_key": model,
                    "prompt_text": meta["text"],
                    "prompt_category": meta.get("category") or rec.get("prompt_category") or "unknown",
                    "persona_id": meta.get("persona_id") or rec.get("persona_id") or "unknown",
                    "prompt_group": meta.get("group") or rec.get("prompt_group") or "unknown",
                    "prompt_subcategory": meta.get("subcategory", ""),
                    "prompt_source": meta.get("source", ""),
                    "prompt_language": meta.get("language", ""),
                    "prompt_expected_format": meta.get("expected_format", ""),
                    "prompt_license": meta.get("licence", ""),
                    "prompt_source_record_id": meta.get("source_record_id", ""),
                    "prompt_length": meta.get("prompt_length", ""),
                })
                results.append(out)
                counts["kept"] += 1
                model_folders[model].add(str(source.parent))
    if missed_prompt_ids:
        raise ValueError(
            "The JSONL files contain prompt IDs missing from the prompt CSV: "
            + ", ".join(sorted(missed_prompt_ids)[:15])
            + (" ..." if len(missed_prompt_ids) > 15 else "")
            + ". Provide the matching prompt CSV to avoid unlabelled prompts."
        )
    if not results:
        raise ValueError("No valid response records loaded.")
    results.sort(key=lambda r: (str(r["model_key"]), str(r["prompt_id"]), str(r.get("sample_index", "")), str(r["record_id"])))
    info = {
        "sources": [str(x) for x in sources],
        "models": sorted(model_folders),
        "model_folders": {k: sorted(v) for k, v in model_folders.items()},
        "stats": dict(counts),
        "metadata_disagreements": dict(metadata_disagreements),
    }
    return results, info


def split_prompts(rows: list[dict], seed: int, fractions: tuple[float, float, float]) -> dict[str, str]:
    by_category: dict[str, list[str]] = defaultdict(list)
    prompt_metadata = {}
    for r in rows:
        pid = r["prompt_id"]
        if pid in prompt_metadata and prompt_metadata[pid] != r["prompt_category"]:
            raise ValueError(f"Inconsistent category across models for prompt ID {pid}")
        prompt_metadata[pid] = r["prompt_category"]
    for pid, cat in prompt_metadata.items():
        by_category[cat].append(pid)
    assignments = {}
    for category, prompt_ids in sorted(by_category.items()):
        items = sorted(prompt_ids)
        rng = random.Random(stable_seed(seed, "split", category))
        rng.shuffle(items)
        # Small rounding discrepancies across categories are acceptable; no response leakage.
        n = len(items)
        n_dev = round(n * fractions[0])
        n_val = round(n * fractions[1])
        if n_dev + n_val > n:
            n_val = n - n_dev
        for i, pid in enumerate(items):
            assignments[pid] = "development" if i < n_dev else ("validation" if i < n_dev + n_val else "test")
    return assignments


def view_name(persona_id: str | None) -> str:
    return VIEW_ALL if persona_id is None else "persona_" + safe_slug(persona_id)


def get_columns(rows: list[dict]) -> list[str]:
    priority = [
        "record_id", "model_key", "prompt_id", "prompt_text", "response_text", "prompt_category",
        "prompt_subcategory", "persona_id", "sample_index", "split", "prompt_group",
    ]
    all_columns = set().union(*(r.keys() for r in rows))
    return [x for x in priority if x in all_columns] + sorted(all_columns - set(priority))


BINARY_COLUMNS = [
    "record_id", "prompt_id", "prompt_text", "response_text", "persona_id",
    "prompt_category", "prompt_subcategory", "sample_index", "model_key", "target_model",
    "label", "split", "prompt_group", "prompt_set_version",
]


def pick_one_per_prompt(candidates: list[dict], rng: random.Random) -> list[dict]:
    by_prompt: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        by_prompt[row["prompt_id"]].append(row)
    selected = []
    for pid in sorted(by_prompt):
        options = sorted(by_prompt[pid], key=lambda r: str(r["record_id"]))
        selected.append(options[rng.randrange(len(options))])
    rng.shuffle(selected)
    return selected


def sample_references(dev_rows: list[dict], target: str, k: int, seed: int, view: str,
                      category: str | None = None) -> tuple[list[dict] | None, str | None]:
    """Return k positive and k negative refs, avoiding repeat prompt IDs within each class.

    Negative references are approximately evenly allocated among non-target models.
    The same reference set is reused for every candidate in this condition.
    """
    rng = random.Random(stable_seed(seed, "references", view, target, k, category or "global"))
    subset = [r for r in dev_rows if category is None or r["prompt_category"] == category]
    pos = pick_one_per_prompt([r for r in subset if r["model_key"] == target], rng)
    by_model = defaultdict(list)
    for row in subset:
        if row["model_key"] != target:
            by_model[row["model_key"]].append(row)
    if len(pos) < k:
        return None, f"only {len(pos)} distinct positive prompts (need {k})"
    if not by_model:
        return None, "no negative models available"
    neg_by_model = {m: pick_one_per_prompt(items, rng) for m, items in sorted(by_model.items())}
    negatives = []
    used_negative_prompts = set()
    shuffled_models = sorted(neg_by_model)
    rng.shuffle(shuffled_models)
    while len(negatives) < k:
        progress = False
        for model in shuffled_models:
            choices = neg_by_model[model]
            eligible = next((item for item in choices if item["prompt_id"] not in used_negative_prompts), None)
            if eligible is None:
                continue
            choices.remove(eligible)
            negatives.append(eligible)
            used_negative_prompts.add(eligible["prompt_id"])
            progress = True
            if len(negatives) >= k:
                break
        if not progress:
            return None, f"only {len(negatives)} distinct negative prompts across models (need {k})"
    positives = pos[:k]
    rng.shuffle(positives)
    rng.shuffle(negatives)
    refs = []
    for label, items in ((1, positives), (0, negatives)):
        for item in items:
            # Important: send only prompt, response and label to Jev; do not reveal model IDs.
            refs.append({
                "label": label,
                "prompt": item["prompt_text"],
                "response": item["response_text"],
                "reference_record_id": item["record_id"],
            })
    rng.shuffle(refs)
    return refs, None


def make_reference_sets(out_dir: Path, rows: list[dict], model_names: list[str],
                        views: dict[str, str | None], sizes: list[int], seed: int) -> tuple[list[dict], list[dict]]:
    manifest = []
    warnings = []
    for view, persona in views.items():
        dev = [r for r in rows if r["split"] == "development" and (persona is None or r["persona_id"] == persona)]
        categories = sorted({r["prompt_category"] for r in rows if persona is None or r["persona_id"] == persona})
        for target in model_names:
            for category in [None] + categories:
                for k in ([0] + sizes) if category is None else sizes:
                    # Size 0: evaluate Jev without examples (negative control).
                    if k == 0:
                        refs, reason = [], None
                    else:
                        refs, reason = sample_references(dev, target, k, seed, view, category)
                    condition = "global" if category is None else "category_matched"
                    if reason:
                        warnings.append({"view": view, "target": target, "category": category or "ALL", "k": k, "reason": reason})
                        continue
                    file_name = ("global" if category is None else "category_" + safe_slug(category)) + f"_k{k:02d}.json"
                    dest = out_dir / "references" / view / safe_slug(target) / file_name
                    # Export only labels and text to Jev; keep record IDs/model identities
                    # in a separate audit file, never in the model's reference state.
                    write_json(dest, {
                        "target_model": target,
                        "view": view,
                        "condition": condition,
                        "category": category,
                        "references_per_class": k,
                        "reference_examples": [
                            {key: ref[key] for key in ("label", "prompt", "response")}
                            for ref in refs
                        ],
                    })
                    audit_dest = out_dir / "reference_audit" / view / safe_slug(target) / file_name
                    development_by_id = {r["record_id"]: r for r in dev}
                    write_json(audit_dest, {
                        "target_model": target,
                        "view": view,
                        "category": category,
                        "references_per_class": k,
                        "references": [
                            {
                                "record_id": ref["reference_record_id"],
                                "actual_model": development_by_id[ref["reference_record_id"]]["model_key"],
                                "prompt_id": development_by_id[ref["reference_record_id"]]["prompt_id"],
                                "label": ref["label"],
                            }
                            for ref in refs
                        ],
                    })
                    manifest.append({
                        "target_model": target,
                        "view": view,
                        "condition": condition,
                        "category": category or "ALL",
                        "references_per_class": k,
                        "positive_count": sum(ref["label"] == 1 for ref in refs),
                        "negative_count": sum(ref["label"] == 0 for ref in refs),
                        "path": str(dest.relative_to(out_dir)),
                        "audit_path": str(audit_dest.relative_to(out_dir)),
                    })
    return manifest, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", type=Path, default=Path("./collector/data/raw"), help="Parent folder containing one subfolder per model")
    ap.add_argument("--prompts", required=True, type=Path, help="Prompt metadata CSV containing source_id and text")
    ap.add_argument("--out", type=Path, default=Path("./collector/data/jev"), help="Destination directory")
    ap.add_argument("--file-name", default="training_v1.jsonl", help="Response filename under each model directory")
    ap.add_argument("--seed", type=int, default=42, help="Reproducible prompt splits and reference sampling")
    ap.add_argument("--train-fraction", type=float, default=0.70, help="Prompt fraction for development/reference pool")
    ap.add_argument("--val-fraction", type=float, default=0.15, help="Prompt fraction for validation")
    ap.add_argument("--personas", nargs="*", default=["P13"], help="Extra persona-only views; all_personas is always produced")
    ap.add_argument("--reference-sizes", nargs="+", type=int, default=[4, 8, 20], help="Examples PER class in reference sets")
    ap.add_argument("--expected-models", type=int, default=7, help="Warn if fewer models found")
    args = ap.parse_args()

    if not 0 < args.train_fraction < 1 or not 0 < args.val_fraction < 1 or args.train_fraction + args.val_fraction >= 1:
        ap.error("Fractions must be positive, and development + validation must be under 1.")
    if any(k <= 0 for k in args.reference_sizes):
        ap.error("Reference sizes must be positive integers (size 0 is generated automatically).")
    if not args.raw_dir.is_dir():
        ap.error(f"Raw directory not found: {args.raw_dir}")
    prompts = read_prompts(args.prompts)
    rows, source_info = load_responses(args.raw_dir, prompts, args.file_name)
    models = source_info["models"]
    views = {VIEW_ALL: None}
    for persona in args.personas:
        if persona.strip():
            views[view_name(persona.strip())] = persona.strip()
    assignments = split_prompts(rows, args.seed,
                                (args.train_fraction, args.val_fraction, 1 - args.train_fraction - args.val_fraction))
    for row in rows:
        row["split"] = assignments[row["prompt_id"]]
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    master_columns = get_columns(rows)
    write_csv(out_dir / "data" / "all_responses.csv", rows, master_columns)
    write_jsonl(out_dir / "data" / "all_responses.jsonl", rows)

    first_by_prompt = {r["prompt_id"]: r for r in rows}
    assignments_table = [{
        "prompt_id": pid,
        "split": assignments[pid],
        "prompt_category": first_by_prompt[pid]["prompt_category"],
        "persona_id": first_by_prompt[pid]["persona_id"],
        "prompt_group": first_by_prompt[pid]["prompt_group"],
    } for pid in sorted(assignments)]
    write_csv(out_dir / "data" / "prompt_assignments.csv", assignments_table,
              ["prompt_id", "split", "prompt_category", "persona_id", "prompt_group"])

    for split in SPLIT_NAMES:
        chunk = [r for r in rows if r["split"] == split]
        write_csv(out_dir / "splits" / f"{split}.csv", chunk, master_columns)

    for view, persona in views.items():
        view_rows = [r for r in rows if persona is None or r["persona_id"] == persona]
        for split in SPLIT_NAMES:
            chunk = [r for r in view_rows if r["split"] == split]
            write_csv(out_dir / "views" / view / f"{split}.csv", chunk, master_columns)
            # Safe candidate input: the Jev caller should extract ONLY prompt and response.
            write_jsonl(out_dir / "jev_candidates" / view / f"{split}.jsonl", [
                {"candidate_id": r["record_id"], "prompt": r["prompt_text"], "response": r["response_text"]}
                for r in chunk
            ])
        for target in models:
            for split in SPLIT_NAMES:
                subset = [r for r in view_rows if r["split"] == split]
                binary = [{**r, "target_model": target, "label": int(r["model_key"] == target)} for r in subset]
                write_csv(out_dir / "binary" / safe_slug(target) / view / f"{split}.csv", binary, BINARY_COLUMNS)

    refs, reference_warnings = make_reference_sets(
        out_dir, rows, models, views, sorted(set(args.reference_sizes)), args.seed
    )
    write_csv(out_dir / "references" / "manifest.csv", refs,
              ["target_model", "view", "condition", "category", "references_per_class",
               "positive_count", "negative_count", "path", "audit_path"])
    write_csv(out_dir / "references" / "skipped.csv", reference_warnings,
              ["view", "target", "category", "k", "reason"])

    model_counts = Counter(r["model_key"] for r in rows)
    split_counts = Counter(r["split"] for r in rows)
    prompt_counts = Counter(assignments.values())
    view_counts = {view: {
        split: sum(1 for r in rows if r["split"] == split and (p is None or r["persona_id"] == p))
        for split in SPLIT_NAMES
    } for view, p in views.items()}
    warnings = []
    if len(models) < args.expected_models:
        warnings.append(f"Found {len(models)} model(s); expected {args.expected_models}. Load the rest to build valid one-vs-rest reference sets.")
    for view, persona in views.items():
        if persona is not None and not any(r["persona_id"] == persona for r in rows):
            warnings.append(f"Persona view '{view}' is empty.")
    if source_info["metadata_disagreements"]:
        warnings.append(f"JSONL vs prompt CSV metadata disagreements (CSV took precedence): {source_info['metadata_disagreements']}")
    if source_info["stats"].get("skipped_errors") or source_info["stats"].get("skipped_empty_responses"):
        warnings.append("Collection errors or empty responses were excluded; see load_stats.")
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": args.seed,
        "input_raw_dir": str(args.raw_dir),
        "input_prompts_csv": str(args.prompts),
        "models": models,
        "model_counts": dict(sorted(model_counts.items())),
        "unique_prompts": len(assignments),
        "prompts_by_split": dict(prompt_counts),
        "responses_by_split": dict(split_counts),
        "responses_by_view_and_split": view_counts,
        "reference_sets_created": len(refs),
        "reference_sets_skipped": len(reference_warnings),
        "reference_sizes_per_class": sorted(set(args.reference_sizes)),
        "load_stats": source_info["stats"],
        "source_files": source_info["sources"],
        "warnings": warnings,
        "methodology": {
            "split_unit": "prompt_id (all models, personas and repetitions grouped together)",
            "stratified_by": "prompt_category",
            "development_use": "Reference examples and exploratory work only",
            "validation_use": "Select Jev question, reference count and threshold",
            "test_use": "Final held-out evaluation; do not select configuration using this set",
            "reference_sampling": "One response per distinct prompt within each label; negatives round-robin across other models; fixed seeded selection",
            "reference_label_definition": "1 = target model; 0 = any other model",
            "category_matched": "References drawn only from one prompt category; skips categories with insufficient development examples",
            "leakage_guard": "No prompt ID appears across splits; references come only from development",
            "warning": "When running Jev, do not include the hidden ground-truth model_key/target_model from candidate CSV in its input state.",
        },
    }
    write_json(out_dir / "summary.json", summary)
    print(f"Models ({len(models)}): {', '.join(models)}")
    print(f"Unique prompts: {len(assignments)}; responses: {len(rows)}")
    print("Prompts by split:", dict(prompt_counts))
    print("Responses by split:", dict(split_counts))
    print("View counts:", view_counts)
    print(f"Reference sets: {len(refs)} created; {len(reference_warnings)} skipped (see references/skipped.csv)")
    for warning in warnings:
        print("WARNING:", warning, file=sys.stderr)
    print("Output:", out_dir.resolve())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
