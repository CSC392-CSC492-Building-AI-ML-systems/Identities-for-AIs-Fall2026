"""Execute one queued mock job with the existing prompt-first fingerprinting workflow.

The backend's current real OpenAI endpoint remains synchronous and separate:
we intentionally do NOT queue user API keys in SQLite.
"""
from __future__ import annotations

from uuid import uuid4

from ..schemas import AnalyzeResponse
from ..services.analysis import MockAnalysisGateway, make_mock_gateway
from .store import SqliteJobStore


class MockJobWorker:
    def __init__(self, store: SqliteJobStore,
                 gateway: MockAnalysisGateway | None = None,
                 *, worker_id: str | None = None):
        self.store = store
        self.gateway = gateway if gateway is not None else make_mock_gateway()
        self.worker_id = worker_id or f"mock-worker-{uuid4()}"

    def run_once(self) -> str | None:
        claimed = self.store.claim_next(self.worker_id)
        if claimed is None:
            return None
        job_id, request = claimed
        try:
            report = self.gateway.analyze(
                request["prompt_text"], use_stage1=request["use_stage1"]
            )
            fingerprint = report.fingerprint
            result = AnalyzeResponse(
                request_id=report.request_id,
                status=fingerprint.final.status,
                model_id=fingerprint.final.model_id,
                stage1_enabled=fingerprint.stage1_enabled,
                model_card_status=report.model_card_status,
                change_status=report.change_status,
                target_queries=report.target_queries,
                report=report.to_dict(),
            ).model_dump(mode="json")
            self.store.complete(job_id, self.worker_id, result)
        except Exception:
            # Never persist exception strings: provider exceptions and future
            # sensitive text can carry raw prompts or API credentials.
            self.store.fail(job_id, self.worker_id, error_code="ANALYSIS_FAILED")
        return job_id
