# Automated test summary

95% confidence intervals (Wilson). "Kept" = results the identifier did not hand off.

## rig_main_run1_final.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 66/83 (80%, CI 70–87%) |
| Flagged "Unknown" (sent for review) | 13 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 56 of 83; right: 54/56 (96%, CI 88–99%) |
| Handed off to the next method | 27; of these, right anyway: 12 |

| Group | Version right |
|---|---|
| banking (BK) | 32/40 (80%, CI 65–90%) |
| no persona (P13) | 9/11 (82%, CI 52–95%) |
| other personas | 25/32 (78%, CI 61–89%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 7/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 5/8 |
| Gemini 3.1 Pro | 7/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 5/8 |
| Qwen3.5 9B | 0/3 |

## rig_main_run2_final.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 67/83 (81%, CI 71–88%) |
| Flagged "Unknown" (sent for review) | 13 |
| Wrong without a flag | 3/83 (4%, CI 1–10%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 56 of 83; right: 55/56 (98%, CI 91–100%) |
| Handed off to the next method | 27; of these, right anyway: 12 |

| Group | Version right |
|---|---|
| banking (BK) | 32/40 (80%, CI 65–90%) |
| no persona (P13) | 9/11 (82%, CI 52–95%) |
| other personas | 26/32 (81%, CI 65–91%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 7/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 7/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 5/8 |
| Qwen3.5 9B | 0/3 |

## rig_main_run3_final.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 66/83 (80%, CI 70–87%) |
| Flagged "Unknown" (sent for review) | 13 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 56 of 83; right: 54/56 (96%, CI 88–99%) |
| Handed off to the next method | 27; of these, right anyway: 12 |

| Group | Version right |
|---|---|
| banking (BK) | 32/40 (80%, CI 65–90%) |
| no persona (P13) | 9/11 (82%, CI 52–95%) |
| other personas | 25/32 (78%, CI 61–89%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 7/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 5/8 |
| Gemini 3.1 Pro | 7/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 5/8 |
| Qwen3.5 9B | 0/3 |

## unknown_closed_final.jsonl (models never seen: claude-haiku-5.5, gpt-6-luna, gpt-6.1-terra)

| Measure | Result |
|---|---|
| Developer right | 24/24 (100%, CI 86–100%) |
| Family right | 9/24 (38%, CI 21–57%) |
| Version right | 23/24 (96%, CI 80–99%) |
| Flagged "Unknown" (sent for review) | 0 |
| Wrong without a flag | 1/24 (4%, CI 1–20%) |
| Hidden or never-seen model called "Unknown" | 23/24 (96%, CI 80–99%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 0 of 24; right: – |
| Handed off to the next method | 24; of these, right anyway: 23 |

| Group | Version right |
|---|---|
| banking (BK) | 12/12 (100%, CI 76–100%) |
| no persona (P13) | 3/3 (100%, CI 44–100%) |
| other personas | 8/9 (89%, CI 56–98%) |
| claude-haiku-5.5 | 8/8 |
| gpt-6-luna | 8/8 |
| gpt-6.1-terra | 7/8 |

## Repeat runs (same setup)

| Hidden model | Runs | Version right (min–max) | Same answer in all runs |
|---|---|---|---|
| none | 3 (rig_main_run1_final.jsonl, rig_main_run2_final.jsonl, rig_main_run3_final.jsonl) | 80–81% | 82/83 |
