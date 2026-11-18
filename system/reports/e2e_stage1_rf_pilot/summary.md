# Unified evaluation summary

Cases: **21**; unique source observations: **15**
Stage 2 requested: random_forest; mode: fallback

## Completed evaluations

### e2e

Status: `completed`. Artifacts: stage1_lr/v1, random_forest/v1.

**Limitation:** Subset/partial E2E diagnostic; NOT full configured pipeline evaluation

- n_cases: 21
- end_to_end_exact_model_accuracy: 19.05%
- resolved: 7
- verified: 7
- drift_detected: 0
- needs_review: 14
- errors: 0
- false_verification_count: 3
- false_drift_alarm_count: 0
- correct_drift_detections: 0
- true_drift_cases: 15
- drift_detection_recall: 0.00%
- correctly_verified_unchanged: 4
- true_unchanged_cases: 6
- stage2_invocations: 14
- false_verification_rate_on_changed: 20.00%
- false_drift_alarm_rate_on_unchanged: 0.00%
- review_rate: 66.67%
- stage2_invocation_rate: 66.67%
- accepted_candidate_accuracy: —

## Blocked or unavailable scopes

None

## Interpretation warnings

- Ground truth is used only for scoring, never passed to models.
- Closed-set LoRA/RF candidates are NOT accepted while review_only; candidate accuracy differs from final resolution.
- The included RF P13 split reuses known prompts and backend features. It is NOT unseen-prompt, unseen-family or deployment-transfer validation.
- Confidence intervals assuming independent samples are not justified for repeated-source swap scenarios.
- Harness mock provider does not measure true judge accuracy; Harness outcomes are diagnostic only.

Raw responses are intentionally omitted from case_results.csv. See dataset source for the original data.
