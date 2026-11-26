"""CPU-only demo: replay one stored six-probe trace through Stage 2.

This is a wiring demonstration, not live-provider validation or new accuracy.
Run from repository root: python system/tools/demo_stage2_replay.py
"""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from system.backend.services.stage2 import make_stage2_gateway, ROOT
from system.backend.ui_results import summarize_stage2_result


def main():
    answers = {}
    calls = []
    class ReplayProvider:
        def send_prompt(self, prompt):
            calls.append(prompt)
            if prompt == 'CPU-only demonstration prompt':
                return 'This initial reply is synthetic.'
            return answers[prompt]
        def close(self):
            pass
    gateway = make_stage2_gateway(provider_factory=lambda key, model: ReplayProvider())
    probes = gateway.workflow.pipeline.stage2.identifiers[0].required_probes()
    source = ROOT/'datasets/collector_raw/agentic-2026-11-26/raw/claude-haiku-4.5/fingerprint_v0.jsonl'
    with source.open(encoding='utf-8') as f:
        records = [json.loads(line) for line in f]
    for p in probes:
        row = next(r for r in records if r['prompt_id']==p.probe_id and r['persona_id']=='BK4'
                   and r['sample_index']==0 and not r.get('error') and (r.get('response_text') or '').strip())
        answers[p.prompt_text] = row['response_text']
    report = gateway.analyze('CPU-only demonstration prompt', api_key='not-a-real-key', target_model='replay-only')
    view = summarize_stage2_result(report, None, gateway.workflow.catalog, gateway.judge)
    out = {'mode':'offline_replay', 'fixture_model_id':'claude-haiku-4.5',
           'initial_reply':'synthetic', 'target_api_calls':0, 'replay_queries':len(calls),
           'target_queries':report.target_queries,'ui_result':view}
    print(json.dumps(out,indent=2,allow_nan=False))
    return 0 if any(x['method']=='random_forest' and x['status']=='candidate' for x in view['method_candidates']) else 1

if __name__=='__main__':
    raise SystemExit(main())
