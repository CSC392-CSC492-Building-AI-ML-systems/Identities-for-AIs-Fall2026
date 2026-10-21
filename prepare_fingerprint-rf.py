#!/usr/bin/env python3
"""Prepare fixed-prompt LLM fingerprinting data BEFORE training a Random Forest.

Input (created by consolidate_fingerprints.py):
    data/processed/fingerprint_v0_all.csv
    data/processed/fingerprint_v0_P13.csv

Output (no model is trained):
    data/ml_ready/rf_all_train.csv
    data/ml_ready/rf_P13_train.csv
    data/ml_ready/rf_P13_test.csv
    data/ml_ready/rf_split_manifest.csv
    data/ml_ready/rf_feature_manifest.json
    data/ml_ready/rf_preparation_report.json

Training files contain only numeric features and the `model_key` target column.
Metadata and null-response rows remain in the *original consolidated files*.

Install: python -m pip install pandas
Run:     python prepare_fingerprint_rf.py
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import sys

import pandas as pd

TARGET = "model_key"
REQUIRED = {
    "record_id", "model_key", "prompt_id", "prompt", "response_text",
    "persona_id", "response_missing", "output_tokens", "latency_ms",
}
NUMERIC_INPUTS = ["output_tokens", "latency_ms"]


def read_consolidated(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise ValueError(f"Missing CSV: {path}. Run consolidate_fingerprints.py first.")
    # Everything initially stays as text: don't turn legitimate response text
    # like 'NA' or 'null' into missing values, or alter identifier formatting.
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    if frame.empty:
        raise ValueError(f"{path}: CSV has no rows")
    for field in ("record_id", "model_key", "prompt_id", "persona_id"):
        if frame[field].str.strip().eq("").any():
            raise ValueError(f"{path}: blank values in required field {field}")
    if frame["record_id"].duplicated().any():
        example = frame.loc[frame["record_id"].duplicated(), "record_id"].iloc[0]
        raise ValueError(f"{path}: duplicate record_id {example!r}")
    recognized = {"true", "false"}
    flag = frame["response_missing"].str.strip().str.lower()
    if not flag.isin(recognized).all():
        raise ValueError(f"{path}: response_missing must contain true/false")
    actual_missing = frame["response_text"].str.strip().eq("")
    if not actual_missing.eq(flag.eq("true")).all():
        raise ValueError(f"{path}: response_missing flag does not match response_text")
    return frame


def validate_persona_subset(full: pd.DataFrame, persona: pd.DataFrame, persona_id: str) -> None:
    if not persona["persona_id"].eq(persona_id).all():
        raise ValueError(f"Persona CSV contains rows other than {persona_id!r}")
    expected = full.loc[full["persona_id"] == persona_id]
    if set(expected["record_id"]) != set(persona["record_id"]):
        raise ValueError("Persona CSV record IDs do not match the selected rows in the all-persona CSV. Rerun consolidation.")
    # Detect an accidental mix of old and new CSV exports.
    indexed = expected.set_index("record_id")
    other = persona.set_index("record_id")
    for field in ("model_key", "prompt_id", "response_text", "response_missing", "output_tokens", "latency_ms"):
        if not indexed.loc[other.index, field].eq(other[field]).all():
            raise ValueError(f"Persona CSV differs from all-persona CSV in {field!r}; rerun consolidation")


def heldout_ids(persona_usable: pd.DataFrame, seed: int) -> tuple[set[str], list[dict[str, object]]]:
    """Select a reproducible held-out response variant per (model, prompt).

    Multiple identical generations are kept on the SAME side of the split;
    otherwise verbatim duplicates could enter both training and testing.
    When all generations are identical, leave the entire group in training.
    This measures new *generations to known prompts*, NOT unseen prompts.
    """
    test_ids: set[str] = set()
    unsplittable: list[dict[str, object]] = []
    for (model, prompt), group in persona_usable.groupby(["model_key", "prompt_id"], sort=True):
        variants = sorted(set(group["response_text"].tolist()),
                          key=lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest())
        if len(variants) < 2:
            unsplittable.append({"model_key": model, "prompt_id": prompt,
                                 "records": len(group), "distinct_response_texts": len(variants)})
            continue
        rng = random.Random(f"{seed}:{model}:{prompt}")
        chosen = variants[rng.randrange(len(variants))]
        # If a variant appears more than once, hold out every exact duplicate.
        test_ids.update(group.loc[group["response_text"] == chosen, "record_id"].tolist())
    return test_ids, unsplittable


def stylistic_features(text: str) -> dict[str, float | int]:
    """Small, interpretable baseline feature set; not a complete fingerprint."""
    words = re.findall(r"\b\w+\b", text, flags=re.UNICODE)
    letters = [ch for ch in text if ch.isalpha()]
    length = len(text)
    return {
        "response_char_count": length,
        "response_word_count": len(words),
        "response_avg_word_length": sum(map(len, words)) / len(words) if words else 0.0,
        "response_unique_word_ratio": len({w.casefold() for w in words}) / len(words) if words else 0.0,
        "response_line_count": text.count("\n") + 1,
        "response_sentence_end_marks": sum(text.count(mark) for mark in ".?!"),
        "response_question_mark_count": text.count("?"),
        "response_exclamation_mark_count": text.count("!"),
        "response_digit_ratio": sum(ch.isdigit() for ch in text) / length if length else 0.0,
        "response_uppercase_ratio": sum(ch.isupper() for ch in letters) / len(letters) if letters else 0.0,
        "response_bullet_line_count": len(re.findall(r"^\s*(?:[-*+]|\d+[.)])\s+", text, re.MULTILINE)),
        "response_markdown_heading_count": len(re.findall(r"^\s{0,3}#{1,6}\s+", text, re.MULTILINE)),
        "response_code_fence_count": text.count("```"),
        "response_first_person_word_count": sum(w.casefold() in {"i", "me", "my", "mine", "we", "us", "our", "ours"} for w in words),
    }


def feature_table(frame: pd.DataFrame, prompt_ids: list[str]) -> pd.DataFrame:
    """One numeric feature vector per usable response (no model training)."""
    if frame.empty:
        raise ValueError("No usable rows available for feature extraction")
    base = pd.DataFrame([stylistic_features(t) for t in frame["response_text"]], index=frame.index)
    base["prompt_char_count"] = frame["prompt"].str.len()
    base["prompt_word_count"] = frame["prompt"].str.count(r"\b\w+\b")
    # Fixed-prompt identity: one-hot, NOT an ordinal integer.
    # Entire prompt vocabulary comes from the *inputs*, never from model labels.
    for pid in prompt_ids:
        base[f"prompt_is__{pid}"] = frame["prompt_id"].eq(pid).astype(int)
    for field in NUMERIC_INPUTS:
        raw = frame[field].str.strip()
        base[field] = pd.to_numeric(raw.replace("", float("nan")), errors="coerce")
        invalid = raw.ne("") & base[field].isna()
        if invalid.any():
            raise ValueError(f"Invalid {field} in {int(invalid.sum())} records, e.g. {frame.loc[invalid, 'record_id'].iloc[0]}")
        base[f"{field}_missing"] = base[field].isna().astype(int)
    # Column order: label first, numeric features only; no metadata leaks.
    return pd.concat([frame[[TARGET]], base], axis=1).reset_index(drop=True)


def safe_write(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all-csv", type=Path, default=Path("data/processed/fingerprint_v0_all.csv"))
    parser.add_argument("--persona-csv", type=Path, default=None,
                        help="Defaults to data/processed/fingerprint_v0_<persona>.csv")
    parser.add_argument("--persona", default="P13")
    parser.add_argument("--output-dir", type=Path, default=Path("data/ml_ready"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if not args.persona.strip():
        parser.error("--persona cannot be blank")
    persona_csv = args.persona_csv or Path("data/processed") / f"fingerprint_v0_{args.persona}.csv"

    try:
        full = read_consolidated(args.all_csv)
        persona = read_consolidated(persona_csv)
        validate_persona_subset(full, persona, args.persona)
        # Text is necessary for this first baseline, so omit missing-text
        # records ONLY from ML feature tables. They remain in the original CSVs.
        usable = full.loc[full["response_missing"].str.lower() == "false"].copy()
        p_usable = usable.loc[usable["persona_id"] == args.persona].copy()
        if p_usable.empty:
            raise ValueError(f"No nonempty responses for persona {args.persona}")
        test_ids, unsplittable = heldout_ids(p_usable, args.seed)
        if not test_ids:
            raise ValueError("Unable to create test set. Need >=2 distinct P13 outputs for at least one model/prompt.")
        in_test = usable["record_id"].isin(test_ids)
        # An identical answer to the same prompt/model could also have occurred
        # under a different persona. Exclude those rows from ALL-persona training
        # to avoid putting a verbatim held-out answer into its training set.
        test_keys = set(zip(p_usable.loc[p_usable["record_id"].isin(test_ids), "model_key"],
                            p_usable.loc[p_usable["record_id"].isin(test_ids), "prompt_id"],
                            p_usable.loc[p_usable["record_id"].isin(test_ids), "response_text"]))
        duplicated_test_answer = pd.Series(
            [(m, p, t) in test_keys for m, p, t in zip(
                usable["model_key"], usable["prompt_id"], usable["response_text"])],
            index=usable.index,
        )
        extra_excluded_ids = set(usable.loc[duplicated_test_answer & ~in_test, "record_id"])
        all_train = usable.loc[~in_test & ~duplicated_test_answer]
        p_train = p_usable.loc[~p_usable["record_id"].isin(test_ids)]
        p_test = p_usable.loc[p_usable["record_id"].isin(test_ids)]
        if p_train.empty or all_train.empty:
            raise ValueError("Training set is empty after splitting")
        test_models = set(p_test["model_key"])
        train_models = set(p_train["model_key"])
        if train_models != test_models:
            raise ValueError(f"P13 train/test model labels differ: train {sorted(train_models)}, test {sorted(test_models)}")
        prompt_ids = sorted(full["prompt_id"].unique().tolist())
        tables = {
            "all_train": feature_table(all_train, prompt_ids),
            f"{args.persona}_train": feature_table(p_train, prompt_ids),
            f"{args.persona}_test": feature_table(p_test, prompt_ids),
        }
        columns = tables["all_train"].columns.tolist()
        if any(t.columns.tolist() != columns for t in tables.values()):
            raise ValueError("Feature-column mismatch across train/test tables")
        out = args.output_dir
        out.mkdir(parents=True, exist_ok=True)
        for split, table in tables.items():
            safe_write(out / f"rf_{split}.csv", table)

        manifest = full[["record_id", "model_key", "prompt_id", "persona_id", "response_missing"]].copy()
        manifest["split"] = "all_train_only"
        manifest.loc[manifest["persona_id"] == args.persona, "split"] = f"{args.persona}_train"
        manifest.loc[manifest["record_id"].isin(test_ids), "split"] = f"{args.persona}_test"
        manifest.loc[manifest["record_id"].isin(extra_excluded_ids), "split"] = "excluded_duplicate_of_test"
        manifest.loc[manifest["response_missing"].str.lower() == "true", "split"] = "excluded_missing_text"
        safe_write(out / "rf_split_manifest.csv", manifest)

        features = columns[1:]
        (out / "rf_feature_manifest.json").write_text(json.dumps({
            "target_column": TARGET,
            "feature_columns": features,
            "prompt_ids": prompt_ids,
            "persona_tested": args.persona,
            "note": "Only feature_columns are predictors. Numeric missing values are blank: impute using training data inside an ML pipeline, not before the split.",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = {
            "seed": args.seed,
            "persona": args.persona,
            "source_all": str(args.all_csv),
            "source_persona": str(persona_csv),
            "total_all_records": len(full),
            "total_persona_records": len(persona),
            "excluded_missing_text_all": len(full) - len(usable),
            "excluded_missing_text_persona": len(persona) - len(p_usable),
            "all_train_rows": len(all_train),
            "excluded_duplicate_of_test_from_all_train": len(extra_excluded_ids),
            "persona_train_rows": len(p_train),
            "common_persona_test_rows": len(p_test),
            "total_numeric_features": len(features),
            "train_by_model_all": dict(sorted(Counter(all_train[TARGET]).items())),
            "train_by_model_persona": dict(sorted(Counter(p_train[TARGET]).items())),
            "test_by_model": dict(sorted(Counter(p_test[TARGET]).items())),
            "all_distinct_personas": sorted(full["persona_id"].unique().tolist()),
            "num_model_labels": full[TARGET].nunique(),
            "num_prompt_ids": len(prompt_ids),
            "persona_groups_without_distinct_test_variant": unsplittable,
            "missing_numeric_in_training_all": {f: int(all_train[f].str.strip().eq("").sum()) for f in NUMERIC_INPUTS},
            "caveat": "This evaluates independent response variants on KNOWN prompts. It is not a test of arbitrary/unseen prompts. Latency and token counts may encode backend/provider effects.",
        }
        (out / "rf_preparation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Fingerprint ML preparation complete — NO classifier trained")
    print(f"  Source records: {len(full)} all / {len(persona)} {args.persona}")
    print(f"  Excluded from ML (missing text): {len(full)-len(usable)} all / {len(persona)-len(p_usable)} {args.persona}")
    print(f"  All-persona training: {len(all_train)} rows ({len(extra_excluded_ids)} duplicate-of-test rows excluded)")
    print(f"  {args.persona} training: {len(p_train)} rows")
    print(f"  Shared {args.persona} test: {len(p_test)} rows")
    print(f"  Numeric features: {len(features)}")
    print(f"  Output directory: {out}")
    if unsplittable:
        print(f"  Note: {len(unsplittable)} model/prompt groups had only one distinct response; no test row selected for those groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
