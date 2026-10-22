#!/usr/bin/env python3
"""Build numeric, leakage-aware train/test tables for fingerprint_v0."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TEXT_FEATURES = [
    "response_char_count",
    "response_word_count",
    "response_avg_word_length",
    "response_unique_word_fraction",
    "response_line_count",
    "response_punctuation_count",
    "response_punctuation_fraction",
    "response_uppercase_letter_fraction",
    "response_uppercase_word_fraction",
    "response_markdown_marker_count",
    "response_bullet_marker_count",
    "response_code_fence_count",
    "response_first_person_pronoun_count",
    "response_first_person_pronoun_fraction",
]
BACKEND_FEATURES = [
    "output_tokens",
    "latency_ms",
    "output_tokens_missing",
    "latency_ms_missing",
]
REQUIRED_COLUMNS = {
    "record_id", "model_key", "prompt_id", "prompt", "response_text",
    "output_tokens", "latency_ms", "persona_id",
}
WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)
FIRST_PERSON_RE = re.compile(
    r"\b(?:i|me|my|mine|we|us|our|ours)\b", re.IGNORECASE
)
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
MARKDOWN_RE = re.compile(r"[#*_>`~|]")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"Input CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(sorted(missing))}")
        return [dict(row) for row in reader]


def is_missing(value: Any) -> bool:
    return value is None or not str(value).strip()


def numeric_or_missing(value: Any) -> tuple[float | None, int]:
    if is_missing(value):
        return None, 1
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, 1
    return (number, 0) if number == number and abs(number) != float("inf") else (None, 1)


def response_features(text: str) -> dict[str, float | int]:
    words = WORD_RE.findall(text)
    lowercase_words = [word.casefold() for word in words]
    alpha = [char for char in text if char.isalpha()]
    punctuation = [char for char in text if not char.isalnum() and not char.isspace()]
    uppercase_words = [word for word in words if any(char.isupper() for char in word)]
    first_person = len(FIRST_PERSON_RE.findall(text))
    return {
        "response_char_count": len(text),
        "response_word_count": len(words),
        "response_avg_word_length": (
            sum(map(len, words)) / len(words) if words else 0.0
        ),
        "response_unique_word_fraction": (
            len(set(lowercase_words)) / len(words) if words else 0.0
        ),
        "response_line_count": len(text.splitlines()),
        "response_punctuation_count": len(punctuation),
        "response_punctuation_fraction": (
            len(punctuation) / len(text) if text else 0.0
        ),
        "response_uppercase_letter_fraction": (
            sum(char.isupper() for char in alpha) / len(alpha) if alpha else 0.0
        ),
        "response_uppercase_word_fraction": (
            len(uppercase_words) / len(words) if words else 0.0
        ),
        "response_markdown_marker_count": len(MARKDOWN_RE.findall(text)),
        "response_bullet_marker_count": len(BULLET_RE.findall(text)),
        "response_code_fence_count": text.count("```"),
        "response_first_person_pronoun_count": first_person,
        "response_first_person_pronoun_fraction": (
            first_person / len(words) if words else 0.0
        ),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", newline="", encoding="utf-8", dir=path.parent,
            prefix=f".{path.stem}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = handle.name
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        Path(temp_path).replace(path)
    finally:
        if temp_path and Path(temp_path).exists():
            Path(temp_path).unlink()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.stem}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = handle.name
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        Path(temp_path).replace(path)
    finally:
        if temp_path and Path(temp_path).exists():
            Path(temp_path).unlink()


def prompt_feature_name(prompt_id: str) -> str:
    return f"prompt_id__{prompt_id}"


def make_features(
    row: dict[str, str], prompt_ids: list[str], feature_columns: list[str]
) -> dict[str, Any]:
    response = row["response_text"]
    prompt = row["prompt"] or ""
    prompt_words = WORD_RE.findall(prompt)
    output_tokens, output_tokens_missing = numeric_or_missing(row.get("output_tokens"))
    latency_ms, latency_missing = numeric_or_missing(row.get("latency_ms"))

    features: dict[str, Any] = response_features(response)
    features.update({
        prompt_feature_name(pid): int(row["prompt_id"] == pid)
        for pid in prompt_ids
    })
    features["prompt_char_count"] = len(prompt)
    features["prompt_word_count"] = len(prompt_words)
    features.update({
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "output_tokens_missing": output_tokens_missing,
        "latency_ms_missing": latency_missing,
    })
    result = {name: features[name] for name in feature_columns}
    result["model_key"] = row["model_key"]
    return result


def record_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        row["record_id"], row["model_key"], row["prompt_id"],
        row["persona_id"], row.get("sample_index", ""),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all-csv", type=Path,
        default=Path("collector/data/processed/fingerprint_v0_all.csv"),
    )
    parser.add_argument(
        "--persona-csv", type=Path,
        default=Path("collector/data/processed/fingerprint_v0_P13.csv"),
    )
    parser.add_argument("--persona", default="P13")
    parser.add_argument("--output-dir", type=Path, default=Path("collector/data/ml_ready"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--split-mode",
        choices=["response-held-out", "prompt-held-out"],
        default="response-held-out",
        help=(
            "Hold out responses to known prompts (default), or hold out entire "
            "prompt IDs to estimate performance on unseen prompts"
        ),
    )
    parser.add_argument(
        "--test-prompt-fraction", type=float, default=0.2,
        help="Fraction of eligible prompt IDs held out in prompt-held-out mode (default: 0.2)",
    )
    args = parser.parse_args(argv)
    if not args.persona.strip():
        parser.error("--persona cannot be blank")
    if not 0 < args.test_prompt_fraction < 1:
        parser.error("--test-prompt-fraction must be between 0 and 1")

    try:
        all_rows = read_csv(args.all_csv)
        persona_rows = read_csv(args.persona_csv)
        if not all_rows or not persona_rows:
            raise ValueError("Both consolidated CSVs must contain at least one data row")
        if any(row["persona_id"] != args.persona for row in persona_rows):
            raise ValueError(f"{args.persona_csv} contains rows outside persona {args.persona}")
        if any(not row["model_key"] or not row["prompt_id"] for row in all_rows):
            raise ValueError("Every row must have a non-empty model_key and prompt_id")

        all_keys = Counter(record_key(row) for row in all_rows)
        persona_keys = Counter(record_key(row) for row in persona_rows)
        if persona_keys - all_keys:
            raise ValueError(
                "Persona CSV has records not present in the all-persona CSV; "
                "regenerate the consolidated CSVs from the same raw inputs"
            )

        prompt_ids = sorted({row["prompt_id"] for row in all_rows})
        one_hot_columns = (
            [prompt_feature_name(pid) for pid in prompt_ids]
            if args.split_mode == "response-held-out" else []
        )
        if len(one_hot_columns) != len(set(one_hot_columns)):
            raise ValueError("Prompt IDs produce colliding one-hot feature names")
        feature_columns = (
            TEXT_FEATURES + one_hot_columns
            + ["prompt_char_count", "prompt_word_count"] + BACKEND_FEATURES
        )

        rng = random.Random(args.seed)
        test_texts: set[tuple[str, str, str]] = set()
        test_prompt_ids: set[str] = set()
        unsplittable: list[dict[str, Any]] = []
        test_keys: set[tuple[str, str, str, str, str]] = set()
        if args.split_mode == "prompt-held-out":
            model_labels = {row["model_key"] for row in persona_rows}
            prompts_by_model = {
                model: {
                    row["prompt_id"] for row in persona_rows
                    if row["model_key"] == model and not is_missing(row["response_text"])
                }
                for model in model_labels
            }
            eligible_prompts = sorted(
                set.intersection(*prompts_by_model.values())
                if prompts_by_model else set()
            )
            if len(eligible_prompts) < 2:
                raise ValueError(
                    "Prompt-held-out evaluation needs at least two prompts with "
                    f"usable {args.persona} responses for every model"
                )
            test_count = max(1, round(len(eligible_prompts) * args.test_prompt_fraction))
            test_count = min(test_count, len(eligible_prompts) - 1)
            test_prompt_ids = set(rng.sample(eligible_prompts, test_count))
            p13_test_rows = [
                row for row in persona_rows
                if row["prompt_id"] in test_prompt_ids and not is_missing(row["response_text"])
            ]
            p13_train_rows = [
                row for row in persona_rows
                if row["prompt_id"] not in test_prompt_ids and not is_missing(row["response_text"])
            ]
            if {row["model_key"] for row in p13_test_rows} != model_labels:
                raise ValueError("Held-out prompts do not contain usable P13 responses for every model")
            if {row["model_key"] for row in p13_train_rows} != model_labels:
                raise ValueError("Training prompts do not contain usable P13 responses for every model")
        else:
            # Select one distinct P13 response string per splittable model/prompt group.
            groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
            for row in persona_rows:
                if not is_missing(row["response_text"]):
                    groups[(row["model_key"], row["prompt_id"])].append(row)
            for (model, prompt_id), rows in sorted(groups.items()):
                unique_texts = sorted({row["response_text"] for row in rows})
                if len(unique_texts) < 2:
                    unsplittable.append({
                        "model_key": model,
                        "prompt_id": prompt_id,
                        "reason": "all usable response strings are identical",
                        "rows": len(rows),
                    })
                    continue
                held_out_text = rng.choice(unique_texts)
                test_texts.add((model, prompt_id, held_out_text))

            test_keys = {
                record_key(row)
                for row in persona_rows
                if (
                    not is_missing(row["response_text"])
                    and (row["model_key"], row["prompt_id"], row["response_text"]) in test_texts
                )
            }
            p13_test_rows = [
                row for row in persona_rows
                if record_key(row) in test_keys and not is_missing(row["response_text"])
            ]
            p13_train_rows = [
                row for row in persona_rows
                if not is_missing(row["response_text"]) and record_key(row) not in test_keys
            ]

        assignments: list[str] = []
        all_train_rows: list[dict[str, str]] = []
        for row in all_rows:
            if is_missing(row["response_text"]):
                assignments.append("missing_response")
                continue
            if args.split_mode == "prompt-held-out":
                if row["prompt_id"] in test_prompt_ids:
                    assignments.append("prompt_test")
                else:
                    assignments.append(
                        f"{args.persona}_train_and_all_train"
                        if row["persona_id"] == args.persona else "all_train"
                    )
                    all_train_rows.append(row)
                continue
            key = record_key(row)
            text_key = (row["model_key"], row["prompt_id"], row["response_text"])
            if key in test_keys and row["persona_id"] == args.persona:
                assignments.append(f"{args.persona}_test")
            elif text_key in test_texts:
                assignments.append("excluded_duplicate_of_test")
            else:
                assignments.append(
                    f"{args.persona}_train_and_all_train"
                    if row["persona_id"] == args.persona else "all_train"
                )
                all_train_rows.append(row)

        all_train = [
            make_features(row, prompt_ids, feature_columns) for row in all_train_rows
        ]
        p13_train = [
            make_features(row, prompt_ids, feature_columns) for row in p13_train_rows
        ]
        p13_test = [
            make_features(row, prompt_ids, feature_columns) for row in p13_test_rows
        ]
        feature_fields = feature_columns + ["model_key"]

        manifest_rows = [
            {
                "record_id": row["record_id"],
                "prompt_id": row["prompt_id"],
                "model_key": row["model_key"],
                "persona_id": row["persona_id"],
                "response_missing": int(is_missing(row["response_text"])),
                "split_assignment": assignment,
            }
            for row, assignment in zip(all_rows, assignments)
        ]
        report = {
            "input_files": {
                "all_personas": str(args.all_csv),
                "selected_persona": str(args.persona_csv),
            },
            "persona": args.persona,
            "seed": args.seed,
            "split_mode": args.split_mode,
            "test_prompt_fraction": (
                args.test_prompt_fraction
                if args.split_mode == "prompt-held-out" else None
            ),
            "held_out_prompt_ids": sorted(test_prompt_ids),
            "split_strategy": (
                (
                    f"Hold out {len(test_prompt_ids)} entire prompt IDs from all personas "
                    "and models; prompts are selected from the set with usable P13 "
                    "responses for every model."
                )
                if args.split_mode == "prompt-held-out"
                else (
                    "Within each (model_key, prompt_id) group, hold out one distinct "
                    "response string when at least two exist. Exact text duplicates "
                    "remain in the same split."
                )
            ),
            "input_records": {
                "all_personas": len(all_rows),
                "selected_persona": len(persona_rows),
                "all_missing_response": sum(is_missing(row["response_text"]) for row in all_rows),
                "persona_missing_response": sum(
                    is_missing(row["response_text"]) for row in persona_rows
                ),
                "all_missing_output_tokens": sum(
                    numeric_or_missing(row.get("output_tokens"))[1] for row in all_rows
                    if not is_missing(row["response_text"])
                ),
                "all_missing_latency_ms": sum(
                    numeric_or_missing(row.get("latency_ms"))[1] for row in all_rows
                    if not is_missing(row["response_text"])
                ),
            },
            "output_records": {
                "rf_all_train": len(all_train),
                f"rf_{args.persona}_train": len(p13_train),
                f"rf_{args.persona}_test": len(p13_test),
            },
            "class_counts": {
                "rf_all_train": dict(sorted(Counter(r["model_key"] for r in all_train).items())),
                f"rf_{args.persona}_train": dict(
                    sorted(Counter(r["model_key"] for r in p13_train).items())
                ),
                f"rf_{args.persona}_test": dict(
                    sorted(Counter(r["model_key"] for r in p13_test).items())
                ),
            },
            "feature_count": len(feature_columns),
            "feature_columns": feature_columns,
            "unsplittable_groups": unsplittable,
            "split_assignment_counts": dict(sorted(Counter(assignments).items())),
            "outputs": [
                "rf_all_train.csv",
                f"rf_{args.persona}_train.csv",
                f"rf_{args.persona}_test.csv",
                "rf_split_manifest.csv",
                "rf_feature_manifest.json",
                "rf_preparation_report.json",
            ],
        }
        feature_manifest = {
            "feature_columns": feature_columns,
            "target": "model_key",
            "prompt_ids": prompt_ids,
            "notes": [
                "All listed predictors are numeric; model_key is the target only.",
                "Rows with missing response text are excluded from feature tables.",
                "Missing output_tokens/latency_ms are left blank and indicated by flags.",
                (
                    "Prompt IDs are one-hot features because this is a fixed-prompt task."
                    if args.split_mode == "response-held-out"
                    else "Prompt-ID one-hot features are omitted to evaluate unseen prompts."
                ),
            ],
        }

        output_files = [
            (args.output_dir / "rf_all_train.csv", all_train, feature_fields),
            (args.output_dir / f"rf_{args.persona}_train.csv", p13_train, feature_fields),
            (args.output_dir / f"rf_{args.persona}_test.csv", p13_test, feature_fields),
            (
                args.output_dir / "rf_split_manifest.csv",
                manifest_rows,
                ["record_id", "prompt_id", "model_key", "persona_id",
                 "response_missing", "split_assignment"],
            ),
        ]
        for path, rows, fields in output_files:
            write_csv(path, rows, fields)
        write_json(args.output_dir / "rf_feature_manifest.json", feature_manifest)
        write_json(args.output_dir / "rf_preparation_report.json", report)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Fingerprint feature preparation complete")
    print(f"  Features: {len(feature_columns)}")
    print(f"  All-persona training rows: {len(all_train)}")
    print(f"  {args.persona} training rows: {len(p13_train)}")
    print(f"  {args.persona} test rows: {len(p13_test)}")
    print(f"  Split mode: {args.split_mode}")
    if test_prompt_ids:
        print(f"  Held-out prompt IDs: {', '.join(sorted(test_prompt_ids))}")
    print(f"  Output directory: {args.output_dir}")
    if unsplittable:
        print(f"  Unsplittable model/prompt groups kept in training: {len(unsplittable)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())