"""Local-only interactive client; never passes API keys on the command line.

From repo root after starting FastAPI:
    python -m system.backend.dev_live_client --model YOUR_OPENAI_MODEL --prompt 'Hello'

This makes *real billable OpenAI API calls*. Harness judge is still mocked.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys

import httpx

LOCAL_URL = 'http://127.0.0.1:8000/api/v1/analyze/live'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, help='OpenAI model/API routing ID, not a fingerprint result')
    parser.add_argument('--prompt', required=True, help='Initial prompt sent to the target AI')
    ns = parser.parse_args(argv)
    key = getpass.getpass('OpenAI development API key (not saved): ')
    if not key.strip():
        print('Key required', file=sys.stderr)
        return 2
    try:
        response = httpx.post(LOCAL_URL, timeout=210.0, json={
            'prompt_text': ns.prompt, 'provider': 'openai',
            'target_model': ns.model, 'api_key': key,
            'use_stage1': False,
        })
    except httpx.RequestError:
        print('Cannot reach the local API. Start the FastAPI server first.', file=sys.stderr)
        return 1
    # Keys, raw prompts, and raw provider outputs are not printed.
    try:
        data = response.json()
    except ValueError:
        print('API returned invalid JSON', file=sys.stderr)
        return 1
    if response.is_error:
        print('API error:', json.dumps(data.get('detail', 'Request rejected')))
        return 1
    summary = {name: data.get(name) for name in (
        'mode', 'request_id', 'status', 'model_id', 'stage1_enabled',
        'model_card_status', 'change_status', 'target_queries')}
    print(json.dumps(summary, indent=2))
    print('NOTE: Real target responses, MOCK judge. No real model identity has been confirmed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
