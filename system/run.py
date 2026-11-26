#!/usr/bin/env python3
"""Repository-root friendly entry point for the isolated fingerprinting subsystem.

Run from any directory, including the parent GitHub repository's root:

    python system/run.py evaluate --rf-pilot --scope all
    python system/run.py config
    python system/run.py test
    python system/run.py example random_forest_real_demo

All relative file arguments and report paths are relative to system/.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SYSTEM_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("evaluate", "config", "test", "example", "training", "onboard-dataset", "onboard-classifier", "onboard-model", "release"),
                        help="Action to execute within system/")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Arguments for the chosen action")
    ns = parser.parse_args(argv)

    # Do not depend on the calling shell's working directory or PYTHONPATH.
    # This also preserves existing paths in the original project, which use
    # catalog/, models/, config/, and reports/ relative to system/.
    os.chdir(SYSTEM_ROOT)
    sys.path.insert(0, str(SYSTEM_ROOT))
    args = ns.arguments
    if args[:1] == ["--"]:
        args = args[1:]

    if ns.command in ("training", "onboard-dataset", "onboard-classifier", "onboard-model", "release"):
        script = {"training":"train_classifiers.py", "onboard-dataset":"onboard_dataset.py", "onboard-classifier":"onboard_classifier.py", "onboard-model":"onboard_model.py", "release":"release_classifiers.py"}[ns.command]
        return subprocess.run([sys.executable, str(SYSTEM_ROOT / "tools" / script), *args], cwd=SYSTEM_ROOT, check=False).returncode

    if ns.command == "evaluate":
        from fingerprinting.eval_cli import main as run_evaluation
        return run_evaluation(args)

    if ns.command == "config":
        # Existing config CLI accepts a mandatory positional YAML path. Add a
        # useful default while keeping its validation logic unchanged.
        config_path = "config/production.yaml"
        if args and not args[0].startswith("-"):
            config_path, args = args[0], args[1:]
        sys.argv = ["fingerprinting.config_cli", config_path, "--root", str(SYSTEM_ROOT), *args]
        from fingerprinting.config_cli import main as inspect_config
        return inspect_config()

    if ns.command == "test":
        if args not in ([], ["--research"], ["--all"]):
            parser.error("test accepts --research or --all; default is core tests")
        start = {(): "tests/core", ("--research",): "tests/research", ("--all",): "tests"}[tuple(args)]
        return subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", start, "-t", ".", "-v"],
            cwd=SYSTEM_ROOT.parent,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
        ).returncode

    if ns.command == "example":
        if not args:
            parser.error("'example' requires an example name, e.g. random_forest_real_demo")
        name, *example_args = args
        if not name.replace("_", "").isalnum() or name.endswith(".py"):
            parser.error("Use an example basename, without .py or path separators")
        script = SYSTEM_ROOT / "examples" / f"{name}.py"
        if not script.is_file():
            parser.error(f"Unknown example {name!r}")
        return subprocess.run([sys.executable, str(script), *example_args],
                              cwd=SYSTEM_ROOT, check=False).returncode
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
