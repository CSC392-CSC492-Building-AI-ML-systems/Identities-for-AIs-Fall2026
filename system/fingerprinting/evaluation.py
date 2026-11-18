"""Separate, offline evaluation runner: measures strategies and pipeline outputs.

Ground truth is used only in this module and never passed to identifiers.
Offline mode uses recorded probe responses, never fabricates missing answers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Sequence

from .interfaces import Stage1Strategy, Stage2Strategy, TargetClient
from .pipeline import FingerprintPipeline
from .schemas import EvaluationCase, IdentificationInput, Observation
from .strategies import ReplayTargetClient


@dataclass(frozen=True)
class EvaluationReport:
    scope: str
    strategy: str
    metrics: dict[str, Any]
    rows: list[dict[str, Any]]
    # Factory provenance is populated for E2E reports (independent reports can
    # be annotated by a higher-level experiment runner in a later milestone).
    config_sha256: str | None = None
    artifact_ids: dict[str, str] = field(default_factory=dict)
    manifest_sha256: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rate(num: int, denom: int) -> float | None:
    return round(num / denom, 4) if denom else None


def _client(probes: dict[str, Observation],
            factory: Callable[[dict[str, Observation]], TargetClient] | None) -> TargetClient:
    return ReplayTargetClient(probes) if factory is None else factory(dict(probes))


class EvaluationRunner:
    """Three independent evaluation scopes; no production routing inside the runner."""

    @staticmethod
    def stage1(cases: Sequence[EvaluationCase], strategy: Stage1Strategy) -> EvaluationReport:
        rows = []
        for case in cases:
            result = strategy.verify(case.request)
            true_changed = case.actual_model_id != case.request.expected_model_id
            decisive = result.verdict in ("verified", "mismatch")
            correct = (result.verdict == "mismatch") == true_changed if decisive else None
            rows.append({
                "case_id": case.case_id, "expected_model": case.request.expected_model_id,
                "actual_model": case.actual_model_id, "actual_family": case.actual_family_id,
                "true_change": true_changed, "verdict": result.verdict,
                "predicted_family": result.predicted_family_id,
                "predicted_model": result.predicted_model_id,
                "family_prediction_correct": (result.predicted_family_id == case.actual_family_id)
                    if result.predicted_family_id is not None else None,
                "model_prediction_correct": (result.predicted_model_id == case.actual_model_id)
                    if result.predicted_model_id is not None else None,
                "decisive_correct": correct})
        n = len(rows)
        decisive_rows = [r for r in rows if r["decisive_correct"] is not None]
        fam = [r["family_prediction_correct"] for r in rows if r["family_prediction_correct"] is not None]
        model = [r["model_prediction_correct"] for r in rows if r["model_prediction_correct"] is not None]
        metrics = {
            "n_cases": n,
            "verification_decision_coverage": _rate(len(decisive_rows), n),
            "verification_decision_accuracy": _rate(sum(r["decisive_correct"] for r in decisive_rows), len(decisive_rows)),
            "family_accuracy_on_predicted": _rate(sum(fam), len(fam)),
            "family_predictions": len(fam),
            "model_accuracy_on_predicted": _rate(sum(model), len(model)),
            "model_predictions": len(model),
            "false_verifications": sum(r["true_change"] and r["verdict"] == "verified" for r in rows),
            "false_mismatch_alarms": sum(not r["true_change"] and r["verdict"] == "mismatch" for r in rows),
            "inconclusive_or_error": sum(r["verdict"] not in ("verified", "mismatch") for r in rows),
        }
        return EvaluationReport("stage1", getattr(strategy, "name", type(strategy).__name__), metrics, rows)

    @staticmethod
    def stage2(cases: Sequence[EvaluationCase], strategy: Stage2Strategy,
               client_factory: Callable[[dict[str, Observation]], TargetClient] | None = None) -> EvaluationReport:
        rows = []
        for case in cases:
            run = strategy.execute(
                IdentificationInput(initial=case.request.initial,
                                    deployment_id=case.request.deployment_id, domain=case.request.domain),
                _client(case.replay_probes, client_factory))
            rows.append({
                "case_id": case.case_id, "actual_model": case.actual_model_id,
                "accepted_model": run.accepted_model_id,
                "selected_method": run.resolved_by,
                "exact_match": run.accepted_model_id == case.actual_model_id,
                "probes_collected": list(run.probe_ids_collected),
                "attempts": [{"method": a.method, "outcome": a.outcome,
                              "candidate_model": a.candidate_model_id,
                              "accepted_model": a.accepted_model_id,
                              "handoff_requested": a.handoff_requested,
                              "score": a.score, "score_type": a.score_type,
                              "duration_ms": a.duration_ms, "reason": a.reason,
                              "diagnostics": {k: v for k, v in a.diagnostics.items()
                                              if k in ("artifact_id", "acceptance_policy",
                                                       "missing_backend", "known_prompt_id",
                                                       "mock_judge", "exception_type")}} for a in run.attempts]
            })
        accepted = [r for r in rows if r["accepted_model"] is not None]
        methods: dict[str, dict[str, Any]] = {}
        for name in ("lora", "harness", "random_forest"):
            attempts = [(r, a) for r in rows for a in r["attempts"] if a["method"] == name]
            if attempts:
                ids = [(r, a) for r, a in attempts
                       if a["outcome"] == "identified" and a["accepted_model"] is not None
                       and a["handoff_requested"] is not True]
                methods[name] = {
                    "attempted": len(attempts),
                    "accepted": len(ids),
                    # Includes unaccepted LoRA guesses to evaluate a review-only classifier.
                    "candidate_predictions": sum(a["candidate_model"] is not None for _, a in attempts),
                    "candidate_correct": sum(a["candidate_model"] == r["actual_model"]
                                             for r, a in attempts if a["candidate_model"] is not None),
                    "candidate_top1_accuracy": _rate(
                        sum(a["candidate_model"] == r["actual_model"]
                            for r, a in attempts if a["candidate_model"] is not None),
                        sum(a["candidate_model"] is not None for _, a in attempts)),
                    "accepted_correct": sum(a["accepted_model"] == r["actual_model"] for r, a in ids),
                    "accepted_accuracy": _rate(
                        sum(a["accepted_model"] == r["actual_model"] for r, a in ids), len(ids)),
                    "errors": sum(a["outcome"] == "error" for _, a in attempts),
                }
        metrics = {
            "n_cases": len(rows), "accepted": len(accepted),
            "acceptance_coverage": _rate(len(accepted), len(rows)),
            "exact_accuracy_all_cases": _rate(sum(r["exact_match"] for r in rows), len(rows)),
            "exact_accuracy_accepted": _rate(sum(r["exact_match"] for r in accepted), len(accepted)),
            "unresolved": len(rows) - len(accepted), "by_method": methods,
        }
        return EvaluationReport("stage2", strategy.name, metrics, rows)

    @staticmethod
    def e2e(cases: Sequence[EvaluationCase], pipeline: FingerprintPipeline,
            client_factory: Callable[[dict[str, Observation]], TargetClient] | None = None) -> EvaluationReport:
        rows = []
        for case in cases:
            result = pipeline.run(case.request, _client(case.replay_probes, client_factory))
            true_changed = (case.request.expected_model_id != case.actual_model_id
                            if case.request.expected_model_id is not None else None)
            rows.append({
                "case_id": case.case_id, "expected_model": case.request.expected_model_id,
                "actual_model": case.actual_model_id, "true_change": true_changed,
                "stage1_verdict": result.stage1.verdict,
                "stage1_enabled": result.stage1_enabled,
                "stage1_predicted_family": result.stage1.predicted_family_id,
                "stage1_predicted_model": result.stage1.predicted_model_id,
                "status": result.final.status, "predicted_model": result.final.model_id,
                "resolved_by": result.final.resolved_by,
                "exact_match": result.final.model_id == case.actual_model_id,
                "attempted_methods": [a.method for a in result.stage2_attempts],
                "stage2_attempts": [{"method": a.method, "outcome": a.outcome,
                                     "candidate_model": a.candidate_model_id,
                                     "accepted_model": a.accepted_model_id,
                                     "score": a.score, "score_type": a.score_type,
                                     "reason": a.reason, "duration_ms": a.duration_ms}
                                    for a in result.stage2_attempts],
                "duration_ms": result.duration_ms,
                "routing_trace": result.routing_trace,
            })
        n = len(rows)
        changed = [r for r in rows if r["true_change"] is True]
        unchanged = [r for r in rows if r["true_change"] is False]
        metrics = {
            "n_cases": n,
            "end_to_end_exact_model_accuracy": _rate(sum(r["exact_match"] for r in rows), n),
            "resolved": sum(r["predicted_model"] is not None for r in rows),
            "verified": sum(r["status"] == "verified" for r in rows),
            "drift_detected": sum(r["status"] == "drift_detected" for r in rows),
            "identified": sum(r["status"] == "identified" for r in rows),
            "stage1_invocations": sum(r["stage1_enabled"] for r in rows),
            "without_expected_model": sum(r["true_change"] is None for r in rows),
            "needs_review": sum(r["status"] == "needs_review" for r in rows),
            "errors": sum(r["status"] == "error" for r in rows),
            "false_verification_count": sum(r["status"] == "verified" for r in changed),
            "false_drift_alarm_count": sum(r["status"] == "drift_detected" for r in unchanged),
            "correct_drift_detections": sum(r["status"] == "drift_detected" for r in changed),
            "true_drift_cases": len(changed),
            "drift_detection_recall": _rate(sum(r["status"] == "drift_detected" for r in changed), len(changed)),
            "correctly_verified_unchanged": sum(r["status"] == "verified" for r in unchanged),
            "true_unchanged_cases": len(unchanged),
            "stage2_invocations": sum(bool(r["attempted_methods"]) for r in rows),
            "attempts_by_method": {m: sum(m in r["attempted_methods"] for r in rows)
                                   for m in ("lora", "harness", "random_forest")},
        }
        return EvaluationReport(
            "e2e", f"{getattr(pipeline.stage1, 'name', 'stage1') if pipeline.stage1_enabled else 'stage1_off'} + {pipeline.stage2.name}",
            metrics, rows, config_sha256=pipeline.config_sha256,
            artifact_ids=dict(pipeline.artifact_ids),
            manifest_sha256=dict(pipeline.manifest_sha256))
