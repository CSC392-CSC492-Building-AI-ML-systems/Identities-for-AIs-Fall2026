"""Interactive local development live-job client for Git Bash on Windows.

Run from repository root (FastAPI AND live worker must already be running):
    python -m system.backend.dev_live_job_client --model gpt-4.1-mini

Either supply --model (unlinked job) or --deployment-id (linked job), e.g.:
    python -m system.backend.dev_live_job_client --deployment-id YOUR_DEPLOYMENT_UUID

This may make seven BILLABLE target-provider requests. Stage 2 mode can explicitly
consent to additional external judge calls; default is no external judge.
Provider key and local bearer token are requested via getpass and never printed.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
import time

import httpx

ROOT = 'http://127.0.0.1:8000/api/v1/fingerprint/live-jobs'


def main(argv: list[str] | None=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    connection = p.add_mutually_exclusive_group(required=True)
    connection.add_argument('--model', help='Provider routing model ID (unlinked job, not fingerprint ground truth)')
    connection.add_argument('--deployment-id', help='Owned deployment ID; backend resolves routing model')
    p.add_argument('--prompt', help='User prompt; omit to type it interactively (avoids shell history)')
    p.add_argument('--timeout', type=int, default=240, help='Maximum seconds to poll (30-600)')
    p.add_argument("--stage2", action="store_true", help="Use the review-only Stage 2 worker")
    p.add_argument("--allow-live-judge", action="store_true", help="Consent to sending probe responses and references to the configured judge")
    args=p.parse_args(argv)
    if args.allow_live_judge and not args.stage2:
        p.error("--allow-live-judge requires --stage2")
    if not 30 <= args.timeout <= 600:
        p.error('--timeout must be between 30 and 600')
    prompt = args.prompt if args.prompt is not None else input('Prompt to analyze: ')
    bearer=getpass.getpass('Local backend bearer token (not echoed): ')
    key=getpass.getpass('OpenAI target API key (not echoed): ')
    if not (prompt.strip() and bearer.strip() and key.strip()):
        print('Prompt, bearer token and API key required',file=sys.stderr)
        return 2
    headers={'Authorization':f'Bearer {bearer}'}
    try:
        with httpx.Client(timeout=15,trust_env=False) as client:
            payload={'prompt_text':prompt,'provider':'openai',
                     'api_key':key,'use_stage1':False}
            if args.stage2:
                payload.update(mode='live_stage2_review',allow_live_judge=args.allow_live_judge)
            if args.deployment_id:
                payload['deployment_id']=args.deployment_id
            else:
                payload['target_model']=args.model
            response=client.post(ROOT,headers=headers,json=payload)
            # Drop references in client flow before polling; strings may remain
            # in Python memory until GC, not secure deletion.
            key=None
            if response.status_code != 202:
                print(f'Live job rejected (HTTP {response.status_code}); details omitted.',file=sys.stderr)
                return 1
            job_id=response.json()['job_id']
            print(f'Queued job {job_id}; polling for up to {args.timeout}s...')
            location=f'{ROOT}/{job_id}'
            deadline=time.monotonic()+args.timeout
            while time.monotonic()<deadline:
                time.sleep(2)
                r=client.get(location,headers=headers)
                if r.status_code!=200:
                    print(f'Could not retrieve job (HTTP {r.status_code})',file=sys.stderr)
                    return 1
                body=r.json()
                if body['status'] in ('completed','failed'):
                    if body['status']=='failed':
                        print('Job failed:',body.get('error_code','ANALYSIS_FAILED'))
                        return 1
                    result=body.get('result') or {}
                    summary={k:result.get(k) for k in (
                        'mode','request_id','status','model_id','stage1_enabled',
                        'model_card_status','change_status','target_queries')}
                    summary['ui_result']=result.get('ui_result')
                    print(json.dumps(summary,indent=2))
                    print('Candidate evidence only; see ui_result.evidence for judge mode. This is NOT verified model attribution.')
                    return 0
        print('Polling timed out. Job may still be running; no automatic retry.',file=sys.stderr)
        return 1
    except httpx.RequestError:
        print('Could not reach local FastAPI server. Check API + worker terminals.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
