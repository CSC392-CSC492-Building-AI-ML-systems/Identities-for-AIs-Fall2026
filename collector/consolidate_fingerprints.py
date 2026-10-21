#!/usr/bin/env python3
"""Combine per-model fingerprint_v0.jsonl files into all-persona and persona CSVs.

Run from the repository root, for example:

    python consolidate_fingerprints.py --prompts prompts/fingerprinting_prompts.yaml

Requires PyYAML (`python -m pip install pyyaml`). Source JSONL files are never
modified. The CSVs are *raw consolidated records*, not ML-ready feature vectors.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required. Install it with: python -m pip install pyyaml") from exc


# Keep important inputs/labels easy to find, followed by all remaining original
# metadata keys. No original JSONL columns are intentionally discarded.
PRIORITY_COLUMNS = [
    "record_id",
    "model_key",              # Classification target (NOT an input feature)
    "prompt_id",
    "prompt",                 # Original YAML text, unmodified
    "response_text",
    "output_tokens",
    "latency_ms",
    "persona_id",
    "sample_index",
    "response_is_null",       # True when JSON response_text is null/absent
    "response_missing",       # True when null or empty/whitespace-only
    "response_missing_expected",  # True when missing with refusal_only policy
    "prompt_group",
    "prompt_source",
    "save_response",
    "source_file",
]
ADDED_COLUMNS = {
    "prompt", "response_is_null", "response_missing", "response_missing_expected",
    "prompt_source", "save_response", "source_file",
}


def read_prompts(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Prompt YAML not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("prompts"), list):
        raise ValueError("Prompt YAML must have a top-level 'prompts' list")

    prompts: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(data["prompts"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"Prompt entry {index} must be a mapping")
        pid, prompt_text = item.get("id"), item.get("text")
        if not isinstance(pid, str) or not pid.strip():
            raise ValueError(f"Prompt entry {index} has no valid string 'id'")
        if not isinstance(prompt_text, str):
            raise ValueError(f"Prompt {pid} has no valid string 'text'")
        if pid in prompts:
            raise ValueError(f"Duplicate prompt ID in YAML: {pid}")
        if item.get("save_response", "full") not in {"full", "refusal_only"}:
            raise ValueError(f"Prompt {pid} has unrecognized save_response policy")
        prompts[pid] = item
    if not prompts:
        raise ValueError("The prompt YAML contains no prompts")
    return prompts


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_no}")
            yield line_no, record


def is_response_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def serialize_cell(value: Any) -> str:
    # CSV cannot represent JSON null separately from an empty string, so the
    # response_is_null and response_missing flags retain that distinction.
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def write_csv_atomic(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Commit by replacing only after writing the complete output successfully.
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", newline="", encoding="utf-8", dir=path.parent,
            prefix=f".{path.stem}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: serialize_cell(row.get(field)) for field in fields})
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def write_json_atomic(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.stem}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(obj, handle, indent=2, ensure_ascii=False, sort_keys=False)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def process(root: Path, prompts_file: Path, output_dir: Path,
            persona: str, source_name: str, expected_models: int) -> dict[str, Any]:
    prompts = read_prompts(prompts_file)
    if not root.is_dir():
        raise ValueError(f"Raw dataset directory not found: {root}")

    # Exact per-model layout: data/raw/<model-folder>/fingerprint_v0.jsonl
    source_paths = sorted(p for p in root.glob(f"*/{source_name}") if p.is_file())
    if not source_paths:
        raise ValueError(f"No {source_name} found one directory below {root}")

    rows: list[dict[str, Any]] = []
    original_keys: set[str] = set()
    model_files: dict[str, list[str]] = defaultdict(list)
    missing_ids: Counter[str] = Counter()
    warnings: list[str] = []
    record_ids: dict[str, str] = {}
    sample_keys: dict[tuple[Any, ...], str] = {}
    duplicate_records = 0
    repeated_sample_keys = 0
    folder_mismatch_files: set[str] = set()
    group_mismatch_ids: set[str] = set()

    for source in source_paths:
        source_label = source.relative_to(root).as_posix()
        seen_models_this_file: set[str] = set()
        file_count = 0
        for line_no, record in read_jsonl(source):
            file_count += 1
            original_keys.update(record.keys())
            location = f"{source_label}:{line_no}"
            pid, model = record.get("prompt_id"), record.get("model_key")
            if not isinstance(pid, str) or not pid:
                raise ValueError(f"Missing/invalid prompt_id at {location}")
            if not isinstance(model, str) or not model:
                raise ValueError(f"Missing/invalid model_key at {location}")
            if pid not in prompts:
                missing_ids[pid] += 1
                # Fail explicitly instead of silently using an empty prompt.
                continue
            spec = prompts[pid]
            seen_models_this_file.add(model)

            if "prompt" in record and record["prompt"] != spec["text"]:
                raise ValueError(f"Existing 'prompt' disagrees with YAML at {location}")
            if (record.get("prompt_group") is not None and spec.get("group") is not None
                    and record["prompt_group"] != spec["group"]):
                group_mismatch_ids.add(pid)

            rid = record.get("record_id")
            if rid is not None:
                identifier = str(rid)
                if identifier in record_ids:
                    duplicate_records += 1
                    if duplicate_records <= 5:
                        warnings.append(
                            f"Duplicate record_id {identifier}: {record_ids[identifier]} and {location}"
                        )
                else:
                    record_ids[identifier] = location

            if record.get("sample_index") is not None and record.get("persona_id") is not None:
                key = (model, pid, record["persona_id"],
                       record["sample_index"], record.get("prompt_set_version"))
                if key in sample_keys:
                    repeated_sample_keys += 1
                    if repeated_sample_keys <= 5:
                        warnings.append(
                            f"Repeated model/prompt/persona/sample_index: "
                            f"{sample_keys[key]} and {location}; preserved both"
                        )
                else:
                    sample_keys[key] = location

            # Do not normalize the original response or overwrite metadata.
            raw_response = record.get("response_text")
            missing = is_response_missing(raw_response)
            policy = spec.get("save_response", "full")
            enriched = dict(record)
            enriched.update({
                "prompt": spec["text"],
                "prompt_source": spec.get("source"),
                "save_response": policy,
                "source_file": source_label,
                "response_is_null": raw_response is None,
                "response_missing": missing,
                "response_missing_expected": missing and policy == "refusal_only",
            })
            rows.append(enriched)

        if file_count == 0:
            warnings.append(f"Source file contains no records: {source_label}")
        if len(seen_models_this_file) > 1:
            warnings.append(
                f"Multiple model_key values in {source_label}: "
                f"{sorted(seen_models_this_file)}"
            )
        if seen_models_this_file:
            for model in seen_models_this_file:
                model_files[model].append(source_label)
            if source.parent.name not in seen_models_this_file:
                folder_mismatch_files.add(source_label)

    if missing_ids:
        message = ", ".join(f"{pid} ({count})" for pid, count in sorted(missing_ids.items()))
        raise ValueError(
            f"Prompt IDs missing from {prompts_file}: {message}. "
            "Fix the YAML or input files before exporting."
        )
    if len(model_files) != expected_models:
        raise ValueError(
            f"Expected {expected_models} distinct model_key values but found "
            f"{len(model_files)}: {', '.join(sorted(model_files)) or '(none)'}. "
            "Use --expected-models N only if this is intentional."
        )
    if group_mismatch_ids:
        warnings.append(
            "prompt_group differs from YAML for prompt IDs: "
            + ", ".join(sorted(group_mismatch_ids))
            + "; original prompt_group values preserved"
        )
    if folder_mismatch_files:
        warnings.append(
            "Model folder name differs from model_key in: "
            + ", ".join(sorted(folder_mismatch_files))
            + "; model_key was used as the label"
        )
    if duplicate_records > 5:
        warnings.append(f"... plus {duplicate_records - 5} additional duplicate record IDs")
    if repeated_sample_keys > 5:
        warnings.append(f"... plus {repeated_sample_keys - 5} additional repeated sample keys")

    persona_rows = [row for row in rows if row.get("persona_id") == persona]
    if not persona_rows:
        raise ValueError(f"No records found for selected persona {persona!r}")

    # Ensure all 5 target classes are represented in the P13 subset too.
    models_all = set(model_files)
    models_subset = {row["model_key"] for row in persona_rows}
    if models_all != models_subset:
        warnings.append(
            f"Persona {persona} is missing models: {sorted(models_all - models_subset)}"
        )

    # Keep stable output ordering independent of JSON key order.
    fields = PRIORITY_COLUMNS + sorted(original_keys - set(PRIORITY_COLUMNS) - ADDED_COLUMNS)
    counts_by_model = Counter(row["model_key"] for row in rows)
    counts_by_persona = Counter(str(row.get("persona_id")) for row in rows)
    by_model_persona: dict[str, dict[str, int]] = {}
    for model in sorted(models_all):
        counts = Counter(str(row.get("persona_id")) for row in rows
                         if row["model_key"] == model)
        by_model_persona[model] = dict(sorted(counts.items()))

    def missing_stats(data: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "total": len(data),
            "null_response_text": sum(bool(r["response_is_null"]) for r in data),
            "missing_response_text": sum(bool(r["response_missing"]) for r in data),
            "expected_missing_refusal_only": sum(
                bool(r["response_missing_expected"]) for r in data
            ),
            "unexpected_missing_response_text": sum(
                bool(r["response_missing"]) and not bool(r["response_missing_expected"])
                for r in data
            ),
        }

    if missing_stats(rows)["unexpected_missing_response_text"]:
        warnings.append("Some response text is missing for prompts that request full storage")
    if len(source_paths) != expected_models:
        warnings.append(
            f"Found {len(source_paths)} source files for {expected_models} model labels"
        )

    name_stem = Path(source_name).stem
    all_path = output_dir / f"{name_stem}_all.csv"
    persona_path = output_dir / f"{name_stem}_{persona}.csv"
    summary_path = output_dir / f"{name_stem}_validation.json"
    report: dict[str, Any] = {
        "source_files": [p.relative_to(root).as_posix() for p in source_paths],
        "prompt_yaml": str(prompts_file),
        "prompt_definitions": len(prompts),
        "model_labels": sorted(models_all),
        "distinct_prompt_ids": len({row["prompt_id"] for row in rows}),
        "distinct_persona_ids": sorted({str(row.get("persona_id")) for row in rows}),
        "all": missing_stats(rows),
        persona: missing_stats(persona_rows),
        "records_per_model": dict(sorted(counts_by_model.items())),
        "records_per_persona": dict(sorted(counts_by_persona.items())),
        "records_per_model_and_persona": by_model_persona,
        "duplicate_record_ids": duplicate_records,
        "repeated_sample_keys": repeated_sample_keys,
        "warnings": warnings,
        "outputs": [str(all_path), str(persona_path)],
    }

    write_csv_atomic(all_path, rows, fields)
    write_csv_atomic(persona_path, persona_rows, fields)
    write_json_atomic(summary_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"),
                        help="Folder containing one subfolder per model (default: data/raw)")
    parser.add_argument("--prompts", type=Path,
                        default=Path("prompts/fingerprinting_prompts.yaml"),
                        help="YAML prompt definitions (default: prompts/fingerprinting_prompts.yaml)")
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"),
                        help="Destination for CSVs and validation report (default: data/processed)")
    parser.add_argument("--persona", default="P13", help="Persona to filter (default: P13)")
    parser.add_argument("--source-name", default="fingerprint_v0.jsonl",
                        help="JSONL filename within each model folder (default: fingerprint_v0.jsonl)")
    parser.add_argument("--expected-models", type=int, default=5,
                        help="Expected number of distinct model labels (default: 5)")
    args = parser.parse_args(argv)
    if args.expected_models < 1:
        parser.error("--expected-models must be at least 1")
    if not args.persona.strip():
        parser.error("--persona cannot be blank")
    if Path(args.source_name).name != args.source_name:
        parser.error("--source-name must be a filename, not a path")

    try:
        report = process(args.raw_dir, args.prompts, args.output_dir, args.persona,
                         args.source_name, args.expected_models)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Consolidation complete")
    print(f"  Models: {', '.join(report['model_labels'])}")
    print(f"  Prompt definitions: {report['prompt_definitions']}")
    print(f"  All records: {report['all']['total']}")
    print(f"  {args.persona} records: {report[args.persona]['total']}")
    print(f"  Missing responses (all): {report['all']['missing_response_text']}"
          f" ({report['all']['expected_missing_refusal_only']} expected by refusal_only policy)")
    print(f"  Missing responses ({args.persona}): {report[args.persona]['missing_response_text']}")
    print("  By model:")
    for model, count in report["records_per_model"].items():
        print(f"    {model}: {count}")
    print("  Outputs:")
    for path in report["outputs"]:
        print(f"    {path}")
    print(f"    {args.output_dir / (Path(args.source_name).stem + '_validation.json')}")
    if report["warnings"]:
        print("  Warnings:")
        for warning in report["warnings"]:
            print(f"    - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
