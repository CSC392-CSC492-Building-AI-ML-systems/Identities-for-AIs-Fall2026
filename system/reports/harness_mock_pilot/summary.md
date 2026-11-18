# Unified evaluation summary

Cases: **2**; unique source observations: **2**
Stage 2 requested: harness; mode: fallback

## Completed evaluations

### stage2/harness

Status: `completed_diagnostic_only`. Artifacts: harness/v1.

**Limitation:** Mock judge runs are PLUMBING-ONLY: no identification-accuracy claim

- n_cases: 2
- accepted: 0
- acceptance_coverage: 0.00%
- exact_accuracy_all_cases: —
- exact_accuracy_accepted: —
- unresolved: 2
- case_coverage_with_candidate: 50.00%
- missing_replay_probe_errors: 0
- mock_judge_attempts: 2
- supported_identity_cases: 2
- out_of_supported_identity_cases: 0
- candidate_top1_accuracy_on_supported_with_candidate: —
- accepted_out_of_supported_identity_count: 0

## Blocked or unavailable scopes

None

## Interpretation warnings

- Ground truth is used only for scoring, never passed to models.
- Closed-set LoRA/RF candidates are NOT accepted while review_only; candidate accuracy differs from final resolution.
- The included RF P13 split reuses known prompts and backend features. It is NOT unseen-prompt, unseen-family or deployment-transfer validation.
- Confidence intervals assuming independent samples are not justified for repeated-source swap scenarios.
- Harness mock provider does not measure true judge accuracy; Harness outcomes are diagnostic only.

Raw responses are intentionally omitted from case_results.csv. See dataset source for the original data.
