import json
import unittest
from dataclasses import asdict

from fingerprinting.schemas import (EvaluationCase, FingerprintRequest,
    IdentificationInput, IdentificationResult, Observation, ProbeQuestion, Stage1Result)
from fingerprinting.pipeline import FingerprintPipeline
from fingerprinting.strategies import (SingleMethodStrategy, FallbackStrategy,
    RunAllStrategy, ReplayTargetClient)
from fingerprinting.testing import StubIdentifier, StubStage1
from fingerprinting.evaluation import EvaluationRunner


def base_request(case_id="c1", expected="llama3.1-8b"):
    return FingerprintRequest(case_id, Observation("Explain recursion", "A recursive function calls itself.", "q1"),
                              expected, "llama")


def stage1(verdict="mismatch", name="hard_route"):
    return StubStage1(name, Stage1Result(
        verdict=verdict, predicted_family_id="llama", family_match=True,
        model_match=(verdict == "verified"), predicted_model_id="llama3.1-8b"))


def method(name, outcome="unknown", chosen="llama3.2-3b", handoff=None, probes=()):
    return StubIdentifier(name, IdentificationResult(
        method=name, outcome=outcome, candidate_model_id=chosen,
        accepted_model_id=chosen if outcome == "identified" else None,
        handoff_requested=handoff), probes)


class StrategyPatternTests(unittest.TestCase):
    def setUp(self):
        self.req = base_request()
        self.p1 = ProbeQuestion("I1", "Who created you?")
        self.p2 = ProbeQuestion("I2", "What model are you?")
        self.responses = {
            "I1": Observation("Who created you?", "I was created by Meta.", "I1"),
            "I2": Observation("What model are you?", "I am a language model.", "I2")}

    def test_stage1_verified_skips_every_stage2_method(self):
        s = stage1("verified")
        lora = method("lora", "identified")
        p = FingerprintPipeline(s, SingleMethodStrategy(lora))
        out = p.run(self.req)
        self.assertEqual((out.final.status, out.final.resolved_by), ("verified", "stage1"))
        self.assertEqual(out.stage2_attempts, [])
        self.assertEqual(len(lora.calls), 0)

    def test_lora_accepted_skips_harness_and_rf(self):
        lora = method("lora", "identified")
        harness, rf = method("harness"), method("random_forest")
        pipeline = FingerprintPipeline(stage1(), FallbackStrategy([lora, harness, rf]))
        result = pipeline.run(self.req)
        self.assertEqual(result.final.status, "drift_detected")
        self.assertEqual(result.final.resolved_by, "lora")
        self.assertEqual([r.method for r in result.stage2_attempts], ["lora"])
        self.assertEqual(len(harness.calls) + len(rf.calls), 0)

    def test_harness_collects_probes_only_after_lora_handoff(self):
        lora = method("lora", "unknown")
        harness = method("harness", "identified", probes=(self.p1, self.p2))
        rf = method("random_forest", "identified")
        client = ReplayTargetClient(self.responses)
        pipeline = FingerprintPipeline(stage1(), FallbackStrategy([lora, harness, rf]))
        result = pipeline.run(self.req, client)
        self.assertEqual(result.final.resolved_by, "harness")
        self.assertEqual(client.asked, ["I1", "I2"])
        self.assertEqual(len(harness.calls), 1)
        self.assertEqual(set(harness.calls[0].probes), {"I1", "I2"})
        self.assertEqual(len(rf.calls), 0)
        self.assertNotIn("expected_model_id", asdict(harness.calls[0]))
        self.assertNotIn("actual_model_id", asdict(harness.calls[0]))

    def test_rf_final_fallback(self):
        chain = FallbackStrategy([method("lora", "unsupported"),
                                  method("harness", "unknown"),
                                  method("random_forest", "identified")])
        out = FingerprintPipeline(stage1(), chain).run(self.req)
        self.assertEqual([x.method for x in out.stage2_attempts],
                         ["lora", "harness", "random_forest"])
        self.assertEqual(out.final.resolved_by, "random_forest")

    def test_stage2_unknown_result_gives_needs_review(self):
        chain = FallbackStrategy([method("lora"), method("harness"), method("random_forest")])
        out = FingerprintPipeline(stage1(), chain).run(self.req)
        self.assertEqual(out.final.status, "needs_review")
        self.assertIsNone(out.final.model_id)

    def test_stage2_can_identify_expected_model_after_stage1_mismatch(self):
        lora = method("lora", "identified", chosen="llama3.1-8b")
        result = FingerprintPipeline(stage1(), SingleMethodStrategy(lora)).run(self.req)
        self.assertEqual(result.final.status, "verified")
        self.assertEqual(result.final.resolved_by, "lora")

    def test_missing_replay_probe_is_an_error_not_fake_answer(self):
        harness = method("harness", "identified", probes=(self.p1, self.p2))
        rf = method("random_forest", "identified")
        client = ReplayTargetClient({"I1": self.responses["I1"]})
        result = FingerprintPipeline(stage1(), FallbackStrategy([harness, rf])).run(self.req, client)
        self.assertEqual(result.stage2_attempts[0].outcome, "error")
        self.assertIn("MissingProbeError", result.stage2_attempts[0].reason)
        self.assertEqual(result.final.resolved_by, "random_forest")
        self.assertEqual(len(harness.calls), 0)

    def test_all_errors_is_system_error(self):
        harness = method("harness", "identified", probes=(self.p1,))
        result = FingerprintPipeline(stage1(), SingleMethodStrategy(harness)).run(self.req)
        self.assertEqual(result.final.status, "error")
        self.assertEqual(result.stage2_attempts[0].outcome, "error")

    def test_handoff_requested_prevents_acceptance(self):
        harness = method("harness", "identified", handoff=True)
        rf = method("random_forest", "identified")
        out = FingerprintPipeline(stage1(), FallbackStrategy([harness, rf])).run(self.req)
        self.assertEqual(out.final.resolved_by, "random_forest")
        self.assertEqual(len(out.stage2_attempts), 2)

    def test_single_method_strategy_independent_of_pipeline(self):
        rf = method("random_forest", "identified")
        out = SingleMethodStrategy(rf).execute(IdentificationInput(initial=self.req.initial))
        self.assertEqual(out.accepted_model_id, "llama3.2-3b")
        self.assertEqual(out.resolved_by, "random_forest")

    def test_compare_all_runs_every_method(self):
        methods = [method("lora", "identified"), method("harness", "identified"),
                   method("random_forest", "identified")]
        out = RunAllStrategy(methods).execute(IdentificationInput(initial=self.req.initial))
        self.assertEqual(len(out.attempts), 3)
        self.assertEqual(out.resolved_by, "lora")  # first accepted by priority
        self.assertEqual([len(m.calls) for m in methods], [1, 1, 1])

    def test_swapping_stage1_strategies_changes_route_without_pipeline_changes(self):
        lora1, lora2 = method("lora", "identified"), method("lora", "identified")
        passed = FingerprintPipeline(stage1("verified", "hard_route"), SingleMethodStrategy(lora1))
        rejected = FingerprintPipeline(stage1("mismatch", "hierarchy_soft"), SingleMethodStrategy(lora2))
        self.assertEqual(passed.run(self.req).final.resolved_by, "stage1")
        self.assertEqual(rejected.run(self.req).final.resolved_by, "lora")
        self.assertEqual(len(lora1.calls), 0)
        self.assertEqual(len(lora2.calls), 1)

    def test_bad_stage1_acceptance_does_not_silently_verify(self):
        bad = StubStage1("bad", Stage1Result("verified", family_match=False, model_match=True))
        result = FingerprintPipeline(bad, SingleMethodStrategy(method("lora", "unknown"))).run(self.req)
        self.assertEqual(result.stage1.verdict, "error")
        self.assertEqual(result.final.status, "needs_review")

    def test_duplicate_stage2_methods_rejected(self):
        with self.assertRaises(ValueError):
            FallbackStrategy([method("lora"), method("lora")])

    def test_results_are_json_ready(self):
        result = FingerprintPipeline(stage1(), SingleMethodStrategy(method("lora", "identified"))).run(self.req)
        data = json.loads(json.dumps(result.to_dict()))
        self.assertEqual(data["stage2_attempts"][0]["method"], "lora")
        self.assertEqual(data["stage2_strategy"], "only_lora")


class EvaluationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.case_same = EvaluationCase("unchanged", base_request("unchanged"),
                 "llama3.1-8b", "llama", "test_dataset", "heldout")
        self.case_drift = EvaluationCase("drift", base_request("drift"),
                 "llama3.2-3b", "llama", "test_dataset", "heldout")

    def test_stage1_independent_evaluation_without_stage2(self):
        rep = EvaluationRunner.stage1([self.case_same, self.case_drift], stage1("mismatch"))
        self.assertEqual(rep.metrics["n_cases"], 2)
        self.assertEqual(rep.metrics["false_mismatch_alarms"], 1)
        self.assertEqual(rep.metrics["verification_decision_accuracy"], 0.5)

    def test_stage2_independent_even_when_stage1_would_verify(self):
        identifier = method("lora", "identified", chosen="llama3.2-3b")
        rep = EvaluationRunner.stage2([self.case_same, self.case_drift], SingleMethodStrategy(identifier))
        self.assertEqual(rep.metrics["accepted"], 2)
        self.assertEqual(rep.metrics["exact_accuracy_all_cases"], 0.5)
        self.assertEqual(len(identifier.calls), 2)

    def test_e2e_metrics_are_distinct_from_strategy_execution(self):
        pipeline = FingerprintPipeline(stage1("mismatch"),
                  SingleMethodStrategy(method("lora", "identified", chosen="llama3.2-3b")))
        rep = EvaluationRunner.e2e([self.case_same, self.case_drift], pipeline)
        self.assertEqual(rep.metrics["correct_drift_detections"], 1)
        self.assertEqual(rep.metrics["false_drift_alarm_count"], 1)
        self.assertEqual(rep.metrics["drift_detection_recall"], 1)
        self.assertEqual(rep.metrics["end_to_end_exact_model_accuracy"], 0.5)
        self.assertEqual(rep.metrics["attempts_by_method"]["lora"], 2)

    def test_evaluator_never_passes_ground_truth_to_identifier(self):
        identifier = method("lora", "identified", chosen="llama3.2-3b")
        EvaluationRunner.stage2([self.case_drift], SingleMethodStrategy(identifier))
        ctx = asdict(identifier.calls[0])
        self.assertNotIn("actual_model_id", ctx)
        self.assertNotIn("expected_model_id", ctx)

    def test_evaluation_reports_json_serializable(self):
        rep = EvaluationRunner.stage2([self.case_drift], SingleMethodStrategy(method("lora")))
        data = json.loads(json.dumps(rep.to_dict()))
        self.assertEqual(data["metrics"]["unresolved"], 1)


if __name__ == "__main__":
    unittest.main()
