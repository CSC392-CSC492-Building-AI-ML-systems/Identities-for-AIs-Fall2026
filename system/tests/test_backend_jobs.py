"""Local, offline FastAPI/SQLite worker tests: never use provider credentials."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from system.backend.app import create_app
from system.backend.jobs.store import JobStateError, SqliteJobStore
from system.backend.jobs.runner import MockJobWorker
from system.backend.services.analysis import make_mock_gateway

REPO_ROOT = Path(__file__).resolve().parents[2]


class JobHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "jobs.sqlite3"
        self.store = SqliteJobStore(self.db_path)
        self.gateway = make_mock_gateway()
        self.client = TestClient(create_app(self.gateway, job_store=self.store))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def submit(self, prompt="Explain recursion"):
        r = self.client.post("/api/v1/fingerprint/jobs", json={"prompt_text": prompt})
        self.assertEqual(r.status_code, 202, r.text)
        return r

    def test_submit_is_queued_not_executed_inline(self):
        response = self.submit()
        data = response.json()
        self.assertEqual(data["mode"], "mock")
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(response.headers["location"], f"/api/v1/fingerprint/jobs/{data['job_id']}")
        job = self.client.get(response.headers["location"])
        self.assertEqual(job.status_code, 200)
        self.assertIsNone(job.json()["result"])
        self.assertIsNone(job.json()["started_at"])
        self.assertEqual(job.json()["attempt_count"], 0)

    def test_completed_results_can_be_polled_and_reloaded(self):
        prompt = "Distinct prompt should never appear in GET results."
        job_id = self.submit(prompt).json()["job_id"]
        other_store = SqliteJobStore(self.db_path)  # independent worker connection
        worker = MockJobWorker(other_store, self.gateway)
        self.assertEqual(worker.run_once(), job_id)
        self.assertIsNone(worker.run_once())
        resp = self.client.get(f"/api/v1/fingerprint/jobs/{job_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["attempt_count"], 1)
        self.assertIsNotNone(data["started_at"])
        self.assertIsNotNone(data["finished_at"])
        self.assertIsNone(data["error_code"])
        self.assertEqual(data["result"]["mode"], "mock")
        self.assertEqual(data["result"]["status"], "needs_review")
        self.assertIsNone(data["result"]["model_id"])
        self.assertEqual(data["result"]["target_queries"],
                         ["UI-INITIAL", "LM-01", "LM-05", "LM-06", "I1", "I2", "V1-15"])
        self.assertNotIn(prompt, resp.text)
        self.assertNotIn("request_json", resp.text)
        self.assertNotIn("worker_id", resp.text)
        # The input has been dropped from the job row after completion.
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT request_json FROM fingerprint_jobs WHERE job_id=?", (job_id,)).fetchone()
        self.assertIsNone(row[0])
        self.assertEqual(SqliteJobStore(self.db_path).get(job_id)["status"], "completed")

    def test_missing_job_returns_404(self):
        resp = self.client.get("/api/v1/fingerprint/jobs/does-not-exist")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json(), {"detail": "Job not found"})

    def test_user_key_is_rejected_and_not_echoed(self):
        secret = "PRIVATE_TEST_KEY_MUST_NOT_LEAK"
        resp = self.client.post("/api/v1/fingerprint/jobs", json={
            "prompt_text": "Hello", "api_key": secret})
        self.assertEqual(resp.status_code, 422)
        self.assertNotIn(secret, resp.text)
        self.assertNotIn(secret, self.db_path.read_bytes().decode('latin1',errors='ignore'))

    def test_manual_responses_and_probes_rejected(self):
        for key in ("response_text", "probes", "target_model", "provider"):
            response = self.client.post("/api/v1/fingerprint/jobs", json={
                "prompt_text": "Hello", key: "unexpected"})
            self.assertEqual(response.status_code, 422, key)

    def test_invalid_prompt_does_not_create_job(self):
        for value in ("", "  \n", 37, "x" * 8001):
            resp = self.client.post("/api/v1/fingerprint/jobs", json={"prompt_text": value})
            self.assertEqual(resp.status_code, 422)
        with closing(sqlite3.connect(self.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM fingerprint_jobs").fetchone()[0]
        self.assertEqual(count, 0)

    def test_stage1_opt_in_rejected_before_queueing(self):
        resp = self.client.post("/api/v1/fingerprint/jobs", json={
            "prompt_text": "Hello", "use_stage1": True})
        self.assertEqual(resp.status_code, 409)
        self.assertIn("confirmed baseline", resp.json()["detail"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM fingerprint_jobs").fetchone()[0], 0)

    def test_openapi_advertises_jobs_and_capabilities(self):
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("post", paths["/api/v1/fingerprint/jobs"])
        self.assertIn("get", paths["/api/v1/fingerprint/jobs/{job_id}"])
        caps = self.client.get("/api/v1/capabilities").json()
        self.assertTrue(caps["durable_mock_jobs_available"])
        self.assertFalse(caps["live_jobs_available"])
        self.assertTrue(caps["job_worker_required"])
        self.assertFalse(caps["synchronous_prototype_only"])

    def test_worker_exception_is_generic_and_input_removed(self):
        class ExplodingGateway:
            def analyze(self, *args, **kwargs):
                raise RuntimeError("DO_NOT_LEAK_PRIVATE_VALUE")
        job_id = self.submit("DO_NOT_LEAK_PRIVATE_PROMPT").json()["job_id"]
        worker = MockJobWorker(self.store, gateway=ExplodingGateway())
        self.assertEqual(worker.run_once(), job_id)
        data = self.client.get(f"/api/v1/fingerprint/jobs/{job_id}").json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_code"], "ANALYSIS_FAILED")
        self.assertIsNone(data["result"])
        self.assertNotIn("DO_NOT_LEAK", json.dumps(data))
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertIsNone(conn.execute("SELECT request_json FROM fingerprint_jobs").fetchone()[0])

    def test_single_claim_owner_enforced(self):
        job_id = self.submit().json()["job_id"]
        claimed = self.store.claim_next("w1")
        self.assertEqual(claimed[0], job_id)
        self.assertEqual(self.store.get(job_id)["status"], "running")
        self.assertIsNone(self.store.claim_next("w2"))
        with self.assertRaises(JobStateError):
            self.store.complete(job_id, "w2", {"status": "completed"})
        self.assertEqual(self.store.get(job_id)["status"], "running")
        self.store.fail(job_id, "w1")
        with self.assertRaises(JobStateError):
            self.store.fail(job_id, "w1")

    def test_concurrent_claims_distinct_jobs(self):
        job_ids = {self.submit(f"prompt-{i}").json()["job_id"] for i in range(10)}
        def claim(worker_id):
            other_store = SqliteJobStore(self.db_path)
            return other_store.claim_next(worker_id)
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(claim, [f"worker-{i}" for i in range(10)]))
        actual = [job_id for job_id, _ in results if job_id]
        self.assertEqual(set(actual), job_ids)
        self.assertEqual(len(actual), 10)
        self.assertIsNone(self.store.claim_next("worker-next"))

    def test_separate_python_worker_process(self):
        job_id = self.submit("This should run outside the HTTP server").json()["job_id"]
        run = subprocess.run(
            [sys.executable, "-m", "system.backend.worker", "--once", "--db-path", str(self.db_path)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn(job_id, run.stdout)
        self.assertEqual(self.store.get(job_id)["status"], "completed")


if __name__ == "__main__":
    unittest.main()
