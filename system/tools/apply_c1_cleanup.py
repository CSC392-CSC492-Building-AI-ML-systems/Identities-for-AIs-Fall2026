#!/usr/bin/env python3
"""C1-only, checked cleanup after overlaying a new system/ ZIP into a repo.

Dry-run by default. Only deletes the 17 approved historical duplicate Python
scripts if matching originals exist under the repository's root scripts/.
Never deletes the root originals, any unknown files, or model artifacts.

From GitHub root: python system/tools/apply_c1_cleanup.py [--apply]
"""
from __future__ import annotations

import argparse
from pathlib import Path

FILENAMES = (
    'compare_with_ovr.py', 'consolidation.py', 'embeddings.py',
    'evaluate_test.py', 'experiment_common.py', 'metrics_common.py',
    'predict_hierarchical.py', 'predict_one.py', 'prepare_supervised_data.py',
    'rich_features.py', 'stylometry.py', 'summarize_validation.py',
    'train_all_targets.py', 'train_baselines.py', 'train_hierarchical.py',
    'train_rich_features.py', 'train_within_family.py',
)


class CleanupRefused(RuntimeError):
    """The old research script and canonical script are not exact matches."""


def cleanup(repo_root: Path, *, apply: bool = False) -> list[str]:
    """Return approved duplicate names, optionally unlinking verified copies.

    Full preflight validation happens *before* any removal. This prevents a
    partially cleaned directory when one or more original files have diverged.
    """
    repo_root = Path(repo_root).resolve(strict=True)
    original = repo_root / 'scripts'
    duplicated = repo_root / 'system' / 'reference_stage1' / 'scripts'
    if not duplicated.exists():
        return []  # Already cleaned or never installed.
    if duplicated.is_symlink() or not duplicated.is_dir():
        raise CleanupRefused('Refusing non-directory or symlinked reference directory')

    names = [name for name in FILENAMES if (duplicated / name).exists() or
             (duplicated / name).is_symlink()]
    for name in names:
        source = duplicated / name
        reference = original / name
        if source.is_symlink() or not source.is_file():
            raise CleanupRefused(f'Unsafe historical copy: {name}')
        if reference.is_symlink() or not reference.is_file():
            raise CleanupRefused(f'Canonical root script missing or symlinked: scripts/{name}')
        if source.read_bytes() != reference.read_bytes():
            raise CleanupRefused(f'Historical script differs from root version: {name}')

    if apply:
        for name in names:
            (duplicated / name).unlink()
        # No blanket rmtree: other files (including locally modified material)
        # must remain unless separately approved.
        if not any(duplicated.iterdir()):
            duplicated.rmdir()
            parent = duplicated.parent
            if not any(parent.iterdir()):
                parent.rmdir()
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='Delete checked duplicate copies (default: dry run)')
    parser.add_argument('--repo-root', type=Path,
                        default=Path(__file__).resolve().parents[2],
                        help='GitHub repository root (normally detected automatically)')
    opts = parser.parse_args()
    try:
        selected = cleanup(opts.repo_root, apply=opts.apply)
    except (CleanupRefused, OSError) as exc:
        parser.exit(1, f'C1 cleanup refused: {exc}\n')
    if not selected:
        print('No approved duplicate Stage 1 scripts found; nothing to remove.')
        return 0
    print(('Removed ' if opts.apply else 'Would remove ') +
          str(len(selected)) + ' exact duplicate copies from system/reference_stage1/scripts/:')
    for item in selected:
        print('  ' + item)
    if not opts.apply:
        print('To apply: python system/tools/apply_c1_cleanup.py --apply')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
