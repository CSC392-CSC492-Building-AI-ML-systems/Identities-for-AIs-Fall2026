#!/usr/bin/env python3
"""Train and evaluate the two fingerprint Random Forest baselines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.pipeline import make_pipeline
except ImportError as exc:
    raise SystemExit(
        "Training dependencies are missing. Install them with: "
        "python -m pip install pandas scikit-learn"
    ) from exc


def read_feature_csv(path: Path) -> tuple[pd.DataFrame, pd.Series]:
    if not path.is_file():
        raise ValueError(f"Feature CSV not found: {path}")
    frame = pd.read_csv(path)
    if "model_key" not in frame.columns:
        raise ValueError(f"{path} must contain the model_key target column")
    if frame.empty:
        raise ValueError(f"{path} contains no feature rows")
    target = frame["model_key"]
    features = frame.drop(columns="model_key")
    if features.empty:
        raise ValueError(f"{path} contains no predictor columns")
    if not all(pd.api.types.is_numeric_dtype(features[column]) for column in features):
        raise ValueError(f"{path} contains non-numeric predictor columns")
    if target.isna().any():
        raise ValueError(f"{path} contains missing model_key labels")
    return features, target


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if hasattr(value, "item"):
        return json_safe(value.item())
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-dir", type=Path, default=Path("collector/data/ml_ready"))
    parser.add_argument("--output-dir", type=Path, default=Path("collector/data/ml_ready"))
    parser.add_argument("--estimators", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if args.estimators < 1:
        parser.error("--estimators must be at least 1")

    try:
        test_x, test_y = read_feature_csv(args.feature_dir / "rf_P13_test.csv")
        preparation_report_path = args.feature_dir / "rf_preparation_report.json"
        preparation_report = (
            json.loads(preparation_report_path.read_text(encoding="utf-8"))
            if preparation_report_path.is_file() else {}
        )
        split_mode = preparation_report.get("split_mode", "unknown")
        held_out_prompt_ids = preparation_report.get("held_out_prompt_ids", [])
        train_sets = {
            "all_personas": args.feature_dir / "rf_all_train.csv",
            "P13_only": args.feature_dir / "rf_P13_train.csv",
        }
        test_columns = list(test_x.columns)
        results: dict[str, Any] = {}
        prediction_rows: list[dict[str, Any]] = []
        importance_rows: list[dict[str, Any]] = []

        for name, path in train_sets.items():
            train_x, train_y = read_feature_csv(path)
            if list(train_x.columns) != test_columns:
                raise ValueError(
                    f"Predictor columns in {path} do not match the shared P13 test set"
                )
            if set(train_y.unique()) != set(test_y.unique()):
                raise ValueError(
                    f"Training and test model classes differ for {name}: "
                    f"train={sorted(train_y.unique())}, test={sorted(test_y.unique())}"
                )

            model = make_pipeline(
                SimpleImputer(strategy="median"),
                RandomForestClassifier(
                    n_estimators=args.estimators,
                    class_weight="balanced",
                    random_state=args.seed,
                    n_jobs=-1,
                ),
            )
            model.fit(train_x, train_y)
            predictions = model.predict(test_x)
            report = classification_report(
                test_y, predictions, output_dict=True, zero_division=0
            )
            results[name] = {
                "training_rows": len(train_x),
                "test_rows": len(test_x),
                "class_counts_train": {
                    str(key): int(value)
                    for key, value in train_y.value_counts().sort_index().items()
                },
                "class_counts_test": {
                    str(key): int(value)
                    for key, value in test_y.value_counts().sort_index().items()
                },
                "accuracy": float(accuracy_score(test_y, predictions)),
                "macro_f1": float(f1_score(test_y, predictions, average="macro")),
                "classification_report": json_safe(report),
            }
            forest = model.named_steps["randomforestclassifier"]
            importance_rows.extend(
                {
                    "experiment": name,
                    "feature": feature,
                    "importance": float(importance),
                }
                for feature, importance in zip(test_columns, forest.feature_importances_)
            )
            prediction_rows.extend(
                {
                    "experiment": name,
                    "test_row": index,
                    "actual_model_key": str(actual),
                    "predicted_model_key": str(predicted),
                    "correct": bool(actual == predicted),
                }
                for index, (actual, predicted) in enumerate(zip(test_y, predictions))
            )

        args.output_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = args.output_dir / "rf_metrics.json"
        metrics_path.write_text(
            json.dumps(
                {
                    "estimators": args.estimators,
                    "seed": args.seed,
                    "feature_count": len(test_columns),
                    "test_file": str(args.feature_dir / "rf_P13_test.csv"),
                    "split_mode": split_mode,
                    "held_out_prompt_ids": held_out_prompt_ids,
                    "experiments": results,
                    "caveat": (
                        (
                            "Both models use the same P13 test set, and all test prompt "
                            "IDs were excluded from training."
                        )
                        if split_mode == "prompt-held-out"
                        else (
                            "Both models use the same P13 test set. This is a fixed-prompt "
                            "evaluation and does not measure generalization to unseen prompts."
                        )
                    ),
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        pd.DataFrame(prediction_rows).to_csv(
            args.output_dir / "rf_predictions.csv", index=False
        )
        pd.DataFrame(importance_rows).sort_values(
            ["experiment", "importance"], ascending=[True, False]
        ).to_csv(args.output_dir / "rf_feature_importances.csv", index=False)

    except (OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Random Forest experiments complete")
    print(f"  Split mode: {split_mode}")
    if held_out_prompt_ids:
        print(f"  Held-out prompts: {', '.join(held_out_prompt_ids)}")
    for name, result in results.items():
        print(
            f"  {name}: accuracy={result['accuracy']:.3f}, "
            f"macro-F1={result['macro_f1']:.3f}, "
            f"train={result['training_rows']}, test={result['test_rows']}"
        )
    print(f"  Results: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
