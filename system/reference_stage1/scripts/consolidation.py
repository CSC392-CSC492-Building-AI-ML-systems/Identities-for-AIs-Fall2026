#!/usr/bin/env python3
"""Loading and splitting helpers retained from the original Jev data preparer.

Reads collector/data/raw/<model>/training_v1.jsonl, joins to the prompt CSV,
then creates deterministic prompt-grouped, category-stratified splits.
This module does not import or contact Jev.
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


