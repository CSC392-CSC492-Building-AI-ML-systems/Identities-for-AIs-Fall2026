# Automated test summary

95% confidence intervals (Wilson). "Kept" = results the identifier did not hand off.

## drift_test.jsonl (drift test)

| Measure | Result |
|---|---|
| No swap: Verified | 0/1 (0%, CI 0–79%) |
| No swap: Needs review (soft alarm) | 0 |
| No swap: false alarm (Drift detected) | 1/1 (100%, CI 21–100%) |
| Swap caught (Drift detected) | – |
| Swap caught or sent for review | – |
| Swap missed (Verified) | – |
| Swapped-in model's version identified | – |
| Swapped-in model's developer identified | – |

| Swap type | Checks | Caught | Review | Missed |
|---|---|---|---|---|

## rig_ablation_judge-only.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 74/83 (89%, CI 81–94%) |
| Version right | 69/83 (83%, CI 74–90%) |
| Flagged "Unknown" (sent for review) | 0 |
| Wrong without a flag | 14/83 (17%, CI 10–26%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 58 of 83; right: 54/58 (93%, CI 84–97%) |
| Handed off to the next method | 25; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 32/40 (80%, CI 65–90%) |
| no persona (P13) | 8/11 (73%, CI 43–90%) |
| other personas | 29/32 (91%, CI 76–97%) |
| Claude Haiku 4.5 | 7/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 4/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 3/8 |
| Llama 3.2 3B | 8/8 |
| Qwen3 8B | 8/8 |
| Qwen3.5 9B | 2/3 |

## rig_ablation_no-fallback.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 69/83 (83%, CI 74–90%) |
| Flagged "Unknown" (sent for review) | 10 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 57/59 (97%, CI 88–99%) |
| Handed off to the next method | 24; of these, right anyway: 12 |

| Group | Version right |
|---|---|
| banking (BK) | 32/40 (80%, CI 65–90%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 27/32 (84%, CI 68–93%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 2/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## rig_ablation_no-misfit.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 0 |
| Wrong without a flag | 11/83 (13%, CI 8–22%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 57/59 (97%, CI 88–99%) |
| Handed off to the next method | 24; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 29/32 (91%, CI 76–97%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 3/8 |
| Llama 3.2 3B | 8/8 |
| Qwen3 8B | 8/8 |
| Qwen3.5 9B | 2/3 |

## rig_ablation_no-selfname.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 73/83 (88%, CI 79–93%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 60 of 83; right: 58/60 (97%, CI 89–99%) |
| Handed off to the next method | 23; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 28/32 (88%, CI 72–95%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## rig_ablation_no-sibling.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 73/83 (88%, CI 79–93%) |
| Version right | 70/83 (84%, CI 75–91%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 7/83 (8%, CI 4–16%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 55/59 (93%, CI 84–97%) |
| Handed off to the next method | 24; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 9/11 (82%, CI 52–95%) |
| other personas | 28/32 (88%, CI 72–95%) |
| Claude Haiku 4.5 | 7/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 4/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## rig_hide_claude-haiku-4.5.jsonl (hidden: Claude Haiku 4.5)

| Measure | Result |
|---|---|
| Developer right | 28/29 (97%, CI 83–99%) |
| Family right | 20/29 (69%, CI 51–83%) |
| Version right | 27/29 (93%, CI 78–98%) |
| Flagged "Unknown" (sent for review) | 1 |
| Wrong without a flag | 1/29 (3%, CI 1–17%) |
| Hidden model called "Unknown" | 7/8 (88%, CI 53–98%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 14 of 29; right: 14/14 (100%, CI 78–100%) |
| Handed off to the next method | 15; of these, right anyway: 13 |

| Group | Version right |
|---|---|
| banking (BK) | 14/16 (88%, CI 64–97%) |
| no persona (P13) | 3/3 (100%, CI 44–100%) |
| other personas | 10/10 (100%, CI 72–100%) |
| Claude Haiku 4.5 | 7/8 |
| Claude Sonnet 5.5 | 8/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 4/5 |

## rig_hide_claude-sonnet-5.5.jsonl (hidden: Claude Sonnet 5.5)

| Measure | Result |
|---|---|
| Developer right | 80/83 (96%, CI 90–99%) |
| Family right | 68/83 (82%, CI 72–89%) |
| Version right | 71/83 (86%, CI 76–92%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 6/83 (7%, CI 3–15%) |
| Hidden model called "Unknown" | 6/8 (75%, CI 41–93%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 55 of 83; right: 51/55 (93%, CI 83–97%) |
| Handed off to the next method | 28; of these, right anyway: 20 |

| Group | Version right |
|---|---|
| banking (BK) | 32/40 (80%, CI 65–90%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 29/32 (91%, CI 76–97%) |
| Claude Haiku 4.5 | 7/8 |
| Claude Sonnet 5.5 | 6/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 3/3 |

## rig_hide_gemini-3.1-pro.jsonl (hidden: Gemini 3.1 Pro)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 75/83 (90%, CI 82–95%) |
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 7/8 (88%, CI 53–98%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 56 of 83; right: 54/56 (96%, CI 88–99%) |
| Handed off to the next method | 27; of these, right anyway: 18 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 27/32 (84%, CI 68–93%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 7/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## rig_hide_gemini-3.8-flash.jsonl (hidden: Gemini 3.8 Flash)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 73/83 (88%, CI 79–93%) |
| Flagged "Unknown" (sent for review) | 5 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 8/8 (100%, CI 68–100%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 55 of 83; right: 52/55 (95%, CI 85–98%) |
| Handed off to the next method | 28; of these, right anyway: 21 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 28/32 (88%, CI 72–95%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 5/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 8/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## rig_hide_gemma3-4b.jsonl (hidden: Gemma 3 4B)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 73/83 (88%, CI 79–93%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Hidden model called "Unknown" | 8/8 (100%, CI 68–100%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 52 of 83; right: 50/52 (96%, CI 87–99%) |
| Handed off to the next method | 31; of these, right anyway: 23 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 28/32 (88%, CI 72–95%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## rig_hide_llama3.1-8b.jsonl (hidden: Llama 3.1 8B)

| Measure | Result |
|---|---|
| Developer right | 82/83 (99%, CI 93–100%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 75/83 (90%, CI 82–95%) |
| Flagged "Unknown" (sent for review) | 3 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 8/8 (100%, CI 68–100%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 56/59 (95%, CI 86–98%) |
| Handed off to the next method | 24; of these, right anyway: 19 |

| Group | Version right |
|---|---|
| banking (BK) | 35/40 (88%, CI 74–95%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 29/32 (91%, CI 76–97%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 5/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 8/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 3/3 |

## rig_hide_llama3.2-3b.jsonl (hidden: Llama 3.2 3B)

| Measure | Result |
|---|---|
| Developer right | 82/83 (99%, CI 93–100%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 4 |
| Wrong without a flag | 7/83 (8%, CI 4–16%) |
| Hidden model called "Unknown" | 6/8 (75%, CI 41–93%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 55 of 83; right: 51/55 (93%, CI 83–97%) |
| Handed off to the next method | 28; of these, right anyway: 21 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 29/32 (91%, CI 76–97%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 5/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 6/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 3/3 |

## rig_hide_qwen3-8b.jsonl (hidden: Qwen3 8B)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 66/83 (80%, CI 70–87%) |
| Flagged "Unknown" (sent for review) | 4 |
| Wrong without a flag | 13/83 (16%, CI 9–25%) |
| Hidden model called "Unknown" | 0/8 (0%, CI 0–32%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 65 of 83; right: 55/65 (85%, CI 74–91%) |
| Handed off to the next method | 18; of these, right anyway: 11 |

| Group | Version right |
|---|---|
| banking (BK) | 30/40 (75%, CI 60–86%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 26/32 (81%, CI 65–91%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 7/8 |
| GPT-5.6 Terra | 5/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 0/8 |
| Qwen3.5 9B | 2/3 |

## rig_hide_qwen3.5-9b.jsonl (hidden: Qwen3.5 9B)

| Measure | Result |
|---|---|
| Developer right | 82/83 (99%, CI 93–100%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 73/83 (88%, CI 79–93%) |
| Flagged "Unknown" (sent for review) | 4 |
| Wrong without a flag | 6/83 (7%, CI 3–15%) |
| Hidden model called "Unknown" | 1/3 (33%, CI 6–79%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 57/59 (97%, CI 88–99%) |
| Handed off to the next method | 24; of these, right anyway: 16 |

| Group | Version right |
|---|---|
| banking (BK) | 35/40 (88%, CI 74–95%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 28/32 (88%, CI 72–95%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 7/8 |
| GPT-5.6 Terra | 5/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 8/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 1/3 |

## rig_main_run1.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 73/83 (88%, CI 79–93%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 60 of 83; right: 58/60 (97%, CI 89–99%) |
| Handed off to the next method | 23; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 28/32 (88%, CI 72–95%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## rig_main_run2.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 74/83 (89%, CI 81–94%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 3/83 (4%, CI 1–10%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 60 of 83; right: 59/60 (98%, CI 91–100%) |
| Handed off to the next method | 23; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 29/32 (91%, CI 76–97%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 7/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## rig_main_run3.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 73/83 (88%, CI 79–93%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 60 of 83; right: 58/60 (97%, CI 89–99%) |
| Handed off to the next method | 23; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 28/32 (88%, CI 72–95%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 2/3 |

## Repeat runs (same setup)

| Hidden model | Runs | Version right (min–max) | Same answer in all runs |
|---|---|---|---|
| none | 3 (rig_main_run1.jsonl, rig_main_run2.jsonl, rig_main_run3.jsonl) | 88–89% | 82/83 |
