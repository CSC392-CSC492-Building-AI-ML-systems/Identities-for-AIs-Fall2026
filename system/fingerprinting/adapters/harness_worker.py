"""Isolated legacy AI Harness worker.

Runs each Harness version in its own interpreter, so independent reference
snapshots and legacy absolute imports cannot contaminate other versions.
Accepts only a JSON object on stdin, prints one delimited JSON result on stdout.
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

MARKER = '__FINGERPRINTING_HARNESS_RESULT__='


def main() -> None:
    if len(sys.argv) != 2:
        raise ValueError('Usage: harness_worker.py <artifact-root>')
    root = Path(sys.argv[1]).resolve()
    agent = root / 'agent'
    cards = root / 'cards'
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    review_only = manifest.get('options', {}).get('reference_abi') == 'catalog_reference_v2'
    if not (agent / 'identify_api.py').is_file() or (not review_only and not (cards / 'cardlib.py').is_file()):
        raise FileNotFoundError('Harness artifact lacks agent/identify_api.py or cards/cardlib.py')
    sys.path.insert(0, str(agent))
    if not review_only:
        sys.path.insert(0, str(cards))
    from identify_api import identify
    import check_chatbot
    if os.environ.get('FINGERPRINTING_DEPLOYMENTS_DIR'):
        check_chatbot.DEPLOYMENTS = Path(os.environ['FINGERPRINTING_DEPLOYMENTS_DIR']).resolve()

    request = json.load(sys.stdin)
    response = identify(
        answers=request['answers'],
        domain=request.get('domain'),
        deployment=None if review_only else request.get('deployment'),
        judge_provider=request['judge_provider'],
        judge_model=request['judge_model'],
        handoff_below=request['handoff_below'],
    )
    print(MARKER + json.dumps(response, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(2)
