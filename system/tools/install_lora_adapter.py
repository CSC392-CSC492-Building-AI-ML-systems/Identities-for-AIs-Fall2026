"""Stage a supplied PEFT LoRA adapter ZIP as a checksummed v1 artifact.

Usage: python tools/install_lora_adapter.py path/to/my_lora_adapter.zip \\
           --base-revision <full-40-char-HF-commit>

No network access or deserialization of executable pickle content. Only the
named safetensors and JSON files are extracted. The published-artifact check
prevents accidental overwrites; training/retraining is out of scope.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'models/lora/v1'
FILENAMES = ('adapter_model.safetensors', 'adapter_config.json')


def install(archive: Path, revision: str) -> None:
    if not re.fullmatch('[0-9a-fA-F]{40}', revision):
        raise ValueError('Use the complete 40-character base-model Hugging Face Git commit SHA')
    mpath = DEST / 'manifest.json'
    manifest = json.loads(mpath.read_text(encoding='utf-8'))
    if any((DEST / name).exists() for name in FILENAMES):
        raise ValueError('v1 already has adapter files; do not overwrite a published artifact')
    with ZipFile(archive) as z:
        data = {}
        for filename in FILENAMES:
            matches = [n for n in z.namelist() if not n.endswith('/') and
                       Path(n).name == filename and not any(p == '..' for p in Path(n).parts)]
            if len(matches) != 1:
                raise ValueError(f'Archive must contain exactly one {filename}')
            if z.getinfo(matches[0]).file_size > 300 * 1024 * 1024:
                raise ValueError(f'{filename} is unexpectedly large')
            data[filename] = z.read(matches[0])
    config = json.loads(data['adapter_config.json'])
    if config.get('task_type') != 'SEQ_CLS':
        raise ValueError('Not a PEFT sequence classification adapter')
    if config.get('base_model_name_or_path') not in (None, 'Qwen/Qwen2.5-1.5B'):
        raise ValueError('Adapter base model differs from notebook')
    from safetensors import safe_open
    # safetensors.safe_open expects a path. Stage temporarily, verify, then finalize.
    DEST.mkdir(parents=True, exist_ok=True)
    tmp = DEST / '.temporary-lora-head.safetensors'
    try:
        tmp.write_bytes(data['adapter_model.safetensors'])
        with safe_open(tmp, framework='pt', device='cpu') as sf:
            keys = list(sf.keys())
        if not any('.score.' in key or key.startswith('score.') for key in keys):
            raise ValueError('Adapter is missing the trained Qwen score head; do not release')
    finally:
        tmp.unlink(missing_ok=True)
    for fn in FILENAMES:
        (DEST / fn).write_bytes(data[fn])
    for row in manifest['required_files']:
        if row['path'] in data:
            row['sha256'] = hashlib.sha256(data[row['path']]).hexdigest()
    manifest['options']['base_model_revision'] = revision.lower()
    manifest['provenance']['status'] = 'adapter_supplied_unverified_inference'
    manifest['provenance']['note'] = (
        'All LoRA files checksummed. Runtime inference and exact-model validation '
        'still required; acceptance remains review_only pending open-set calibration.')
    mpath.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Installed {archive.name} -> {DEST}; LoRA is now artifact-ready.')
    print('Next: install requirements-lora.txt and test real inference; do not call this calibrated.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('adapter_zip', type=Path)
    ap.add_argument('--base-revision', required=True)
    args = ap.parse_args()
    try:
        install(args.adapter_zip, args.base_revision)
    except Exception as exc:
        sys.exit(f'Failed to install LoRA adapter: {exc}')
