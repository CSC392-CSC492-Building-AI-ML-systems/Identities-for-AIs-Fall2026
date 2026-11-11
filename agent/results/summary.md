# Automated test summary

95% confidence intervals (Wilson). "Kept" = results the identifier did not hand off.

## drift_test.jsonl (drift test)

| Measure | Result |
|---|---|
| No swap: Verified | 29/40 (72%, CI 57–84%) |
| No swap: Needs review (soft alarm) | 6 |
| No swap: false alarm (Drift detected) | 5/40 (12%, CI 5–26%) |
| Swap caught (Drift detected) | 388/400 (97%, CI 95–98%) |
| Swap caught or sent for review | 398/400 (100%, CI 98–100%) |
| Swap missed (Verified) | 2/400 (0%, CI 0–2%) |
| Swapped-in model's version identified | 329/400 (82%, CI 78–86%) |
| Swapped-in model's developer identified | 390/400 (98%, CI 95–99%) |

| Swap type | Checks | Caught | Review | Missed |
|---|---|---|---|---|
| same line | 12 | 12 | 0 | 0 |
| same developer | 40 | 36 | 2 | 2 |
| other developer | 348 | 340 | 8 | 0 |

## rig_ablation_judge-only.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 74/83 (89%, CI 81–94%) |
| Version right | 68/83 (82%, CI 72–89%) |
| Flagged "Unknown" (sent for review) | 2 |
| Wrong without a flag | 13/83 (16%, CI 9–25%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 56 of 83; right: 53/56 (95%, CI 85–98%) |
| Handed off to the next method | 27; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 32/40 (80%, CI 65–90%) |
| no persona (P13) | 8/11 (73%, CI 43–90%) |
| other personas | 28/32 (88%, CI 72–95%) |
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
| Qwen3.5 9B | 1/3 |

## rig_ablation_no-fallback.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 68/83 (82%, CI 72–89%) |
| Flagged "Unknown" (sent for review) | 11 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 58 of 83; right: 56/58 (97%, CI 88–99%) |
| Handed off to the next method | 25; of these, right anyway: 12 |

| Group | Version right |
|---|---|
| banking (BK) | 32/40 (80%, CI 65–90%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 26/32 (81%, CI 65–91%) |
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
| Qwen3.5 9B | 1/3 |

## rig_ablation_no-misfit.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 71/83 (86%, CI 76–92%) |
| Flagged "Unknown" (sent for review) | 1 |
| Wrong without a flag | 11/83 (13%, CI 8–22%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 58 of 83; right: 56/58 (97%, CI 88–99%) |
| Handed off to the next method | 25; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 28/32 (88%, CI 72–95%) |
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
| Qwen3.5 9B | 1/3 |

## rig_ablation_no-selfname.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 7 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 57/59 (97%, CI 88–99%) |
| Handed off to the next method | 24; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 27/32 (84%, CI 68–93%) |
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
| Qwen3.5 9B | 1/3 |

## rig_ablation_no-sibling.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 73/83 (88%, CI 79–93%) |
| Version right | 69/83 (83%, CI 74–90%) |
| Flagged "Unknown" (sent for review) | 8 |
| Wrong without a flag | 6/83 (7%, CI 3–15%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 57 of 83; right: 54/57 (95%, CI 86–98%) |
| Handed off to the next method | 26; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 9/11 (82%, CI 52–95%) |
| other personas | 27/32 (84%, CI 68–93%) |
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
| Qwen3.5 9B | 1/3 |

## rig_hide_claude-haiku-4.5.jsonl (hidden: Claude Haiku 4.5)

| Measure | Result |
|---|---|
| Developer right | 82/83 (99%, CI 93–100%) |
| Family right | 69/83 (83%, CI 74–90%) |
| Version right | 71/83 (86%, CI 76–92%) |
| Flagged "Unknown" (sent for review) | 7 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 7/8 (88%, CI 53–98%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 51 of 83; right: 49/51 (96%, CI 87–99%) |
| Handed off to the next method | 32; of these, right anyway: 22 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 27/32 (84%, CI 68–93%) |
| Claude Haiku 4.5 | 7/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 1/3 |

## rig_hide_claude-sonnet-5.5.jsonl (hidden: Claude Sonnet 5.5)

| Measure | Result |
|---|---|
| Developer right | 80/83 (96%, CI 90–99%) |
| Family right | 68/83 (82%, CI 72–89%) |
| Version right | 70/83 (84%, CI 75–91%) |
| Flagged "Unknown" (sent for review) | 8 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 7/8 (88%, CI 53–98%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 52 of 83; right: 49/52 (94%, CI 84–98%) |
| Handed off to the next method | 31; of these, right anyway: 21 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 27/32 (84%, CI 68–93%) |
| Claude Haiku 4.5 | 7/8 |
| Claude Sonnet 5.5 | 7/8 |
| GPT-5.6 Luna | 6/8 |
| GPT-5.6 Terra | 6/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 1/3 |

## rig_hide_gemini-3.1-pro.jsonl (hidden: Gemini 3.1 Pro)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 75/83 (90%, CI 82–95%) |
| Version right | 71/83 (86%, CI 76–92%) |
| Flagged "Unknown" (sent for review) | 7 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 7/8 (88%, CI 53–98%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 55 of 83; right: 53/55 (96%, CI 88–99%) |
| Handed off to the next method | 28; of these, right anyway: 18 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 26/32 (81%, CI 65–91%) |
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
| Qwen3.5 9B | 1/3 |

## rig_hide_gemini-3.8-flash.jsonl (hidden: Gemini 3.8 Flash)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 8/8 (100%, CI 68–100%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 54 of 83; right: 51/54 (94%, CI 85–98%) |
| Handed off to the next method | 29; of these, right anyway: 21 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 27/32 (84%, CI 68–93%) |
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
| Qwen3.5 9B | 1/3 |

## rig_hide_gemma3-4b.jsonl (hidden: Gemma 3 4B)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 7 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Hidden model called "Unknown" | 8/8 (100%, CI 68–100%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 51 of 83; right: 49/51 (96%, CI 87–99%) |
| Handed off to the next method | 32; of these, right anyway: 23 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 27/32 (84%, CI 68–93%) |
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
| Qwen3.5 9B | 1/3 |

## rig_hide_gpt-5.6-luna.jsonl (hidden: GPT-5.6 Luna)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 72/83 (87%, CI 78–92%) |
| Version right | 67/83 (81%, CI 71–88%) |
| Flagged "Unknown" (sent for review) | 8 |
| Wrong without a flag | 8/83 (10%, CI 5–18%) |
| Hidden model called "Unknown" | 0/8 (0%, CI 0–32%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 57 of 83; right: 52/57 (91%, CI 81–96%) |
| Handed off to the next method | 26; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 24/32 (75%, CI 58–87%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 0/8 |
| GPT-5.6 Terra | 8/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 5/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 1/3 |

## rig_hide_gpt-5.6-terra.jsonl (hidden: GPT-5.6 Terra)

| Measure | Result |
|---|---|
| Developer right | 82/83 (99%, CI 93–100%) |
| Family right | 73/83 (88%, CI 79–93%) |
| Version right | 69/83 (83%, CI 74–90%) |
| Flagged "Unknown" (sent for review) | 7 |
| Wrong without a flag | 7/83 (8%, CI 4–16%) |
| Hidden model called "Unknown" | 1/8 (12%, CI 2–47%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 56 of 83; right: 53/56 (95%, CI 85–98%) |
| Handed off to the next method | 27; of these, right anyway: 16 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 25/32 (78%, CI 61–89%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 8/8 |
| GPT-5.6 Terra | 1/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 1/3 |

## rig_hide_llama3.1-8b.jsonl (hidden: Llama 3.1 8B)

| Measure | Result |
|---|---|
| Developer right | 82/83 (99%, CI 93–100%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 73/83 (88%, CI 79–93%) |
| Flagged "Unknown" (sent for review) | 5 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 8/8 (100%, CI 68–100%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 57 of 83; right: 54/57 (95%, CI 86–98%) |
| Handed off to the next method | 26; of these, right anyway: 19 |

| Group | Version right |
|---|---|
| banking (BK) | 35/40 (88%, CI 74–95%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 27/32 (84%, CI 68–93%) |
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
| Qwen3.5 9B | 1/3 |

## rig_hide_llama3.2-3b.jsonl (hidden: Llama 3.2 3B)

| Measure | Result |
|---|---|
| Developer right | 82/83 (99%, CI 93–100%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 70/83 (84%, CI 75–91%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 7/83 (8%, CI 4–16%) |
| Hidden model called "Unknown" | 6/8 (75%, CI 41–93%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 53 of 83; right: 49/53 (92%, CI 82–97%) |
| Handed off to the next method | 30; of these, right anyway: 21 |

| Group | Version right |
|---|---|
| banking (BK) | 33/40 (82%, CI 68–91%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 27/32 (84%, CI 68–93%) |
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
| Qwen3.5 9B | 1/3 |

## rig_hide_qwen3-8b.jsonl (hidden: Qwen3 8B)

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 6 |
| Wrong without a flag | 5/83 (6%, CI 3–13%) |
| Hidden model called "Unknown" | 7/8 (88%, CI 53–98%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 57 of 83; right: 54/57 (95%, CI 86–98%) |
| Handed off to the next method | 26; of these, right anyway: 18 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 10/11 (91%, CI 62–98%) |
| other personas | 28/32 (88%, CI 72–95%) |
| Claude Haiku 4.5 | 8/8 |
| Claude Sonnet 5.5 | 8/8 |
| GPT-5.6 Luna | 7/8 |
| GPT-5.6 Terra | 5/8 |
| Gemini 3.1 Pro | 8/8 |
| Gemini 3.8 Flash | 7/8 |
| Gemma 3 4B | 8/8 |
| Llama 3.1 8B | 6/8 |
| Llama 3.2 3B | 7/8 |
| Qwen3 8B | 7/8 |
| Qwen3.5 9B | 1/3 |

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
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 7 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 57/59 (97%, CI 88–99%) |
| Handed off to the next method | 24; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 27/32 (84%, CI 68–93%) |
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
| Qwen3.5 9B | 1/3 |

## rig_main_run2.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 77/83 (93%, CI 85–97%) |
| Version right | 73/83 (88%, CI 79–93%) |
| Flagged "Unknown" (sent for review) | 7 |
| Wrong without a flag | 3/83 (4%, CI 1–10%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 58/59 (98%, CI 91–100%) |
| Handed off to the next method | 24; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 28/32 (88%, CI 72–95%) |
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
| Qwen3.5 9B | 1/3 |

## rig_main_run3.jsonl

| Measure | Result |
|---|---|
| Developer right | 81/83 (98%, CI 92–99%) |
| Family right | 76/83 (92%, CI 84–96%) |
| Version right | 72/83 (87%, CI 78–92%) |
| Flagged "Unknown" (sent for review) | 7 |
| Wrong without a flag | 4/83 (5%, CI 2–12%) |
| Kept by the identifier (fit ≥ 0.7, version known) | 59 of 83; right: 57/59 (97%, CI 88–99%) |
| Handed off to the next method | 24; of these, right anyway: 15 |

| Group | Version right |
|---|---|
| banking (BK) | 34/40 (85%, CI 71–93%) |
| no persona (P13) | 11/11 (100%, CI 74–100%) |
| other personas | 27/32 (84%, CI 68–93%) |
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
| Qwen3.5 9B | 1/3 |

## Repeat runs (same setup)

| Hidden model | Runs | Version right (min–max) | Same answer in all runs |
|---|---|---|---|
| none | 3 (rig_main_run1.jsonl, rig_main_run2.jsonl, rig_main_run3.jsonl) | 87–88% | 82/83 |
