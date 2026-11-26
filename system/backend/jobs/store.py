"""Small SQLite-backed job store for the *mock-only* Milestone 3 worker.

The queue is deliberately SQLite rather than Redis/RQ to make the first
backend milestone runnable on Windows Git Bash without external services.
Each method opens a short-lived connection. BEGIN IMMEDIATE atomically claims
one queued job across independent worker processes.

SECURITY: queued jobs temporarily store a user's *prompt* in plaintext in a
local database. No API keys or provider credentials are permitted here. Use
only on localhost, without real users or confidential prompts. SQLite WAL and
backups can retain old bytes; removing input_json on completion is not secure
erasure. Production needs encryption/retention/auth/ownership controls.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


class JobStateError(RuntimeError):
    """A job has already moved to another state or worker."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


SYSTEM_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = SYSTEM_ROOT / ".local" / "jobs.sqlite3"


class SqliteJobStore:
    def __init__(self, db_path: str | Path | None = None):
        self.path = Path(db_path or DEFAULT_DB_PATH).expanduser().resolve()
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(str(self.path), timeout=5.0)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA busy_timeout=5000")
            yield con
        finally:
            con.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""
                CREATE TABLE IF NOT EXISTS fingerprint_jobs (
                    job_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL CHECK(mode = 'mock'),
                    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    request_json TEXT,
                    result_json TEXT,
                    error_code TEXT,
                    worker_id TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_pending ON fingerprint_jobs(status, created_at)")
            con.commit()

    def enqueue_mock(self, prompt_text: str, *, use_stage1: bool = False) -> dict[str, Any]:
        if not isinstance(prompt_text, str) or not prompt_text.strip() or len(prompt_text) > 8000:
            raise ValueError("Prompt must be a nonempty string of at most 8000 characters")
        if use_stage1:
            raise ValueError("Stage 1 requires a confirmed baseline; unavailable in mock jobs")
        job_id = str(uuid4())
        now = utcnow()
        input_data = json.dumps({"prompt_text": prompt_text, "use_stage1": False})
        with self._connect() as con:
            con.execute("""
                INSERT INTO fingerprint_jobs(job_id,mode,status,created_at,updated_at,request_json)
                VALUES (?, 'mock', 'queued', ?, ?, ?)
            """, (job_id, now, now, input_data))
            con.commit()
        return {"job_id": job_id, "status": "queued", "mode": "mock", "created_at": now}

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, Any]:
        # Never expose prompt, worker ID, or internal stack traces through HTTP.
        return {
            "schema_version": "1.0",
            "job_id": row["job_id"],
            "mode": row["mode"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "attempt_count": row["attempt_count"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error_code": row["error_code"],
        }

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM fingerprint_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._public(row) if row else None

    def claim_next(self, worker_id: str) -> tuple[str, dict[str, Any]] | None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("worker_id must be 1-128 characters")
        with self._connect() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                row = con.execute("""
                    SELECT job_id, request_json FROM fingerprint_jobs
                    WHERE status='queued' ORDER BY created_at, rowid LIMIT 1
                """).fetchone()
                if row is None:
                    con.commit()
                    return None
                now = utcnow()
                count = con.execute("""
                    UPDATE fingerprint_jobs SET status='running', worker_id=?,
                        updated_at=?, started_at=?, attempt_count=attempt_count+1
                    WHERE job_id=? AND status='queued'
                """, (worker_id, now, now, row["job_id"])).rowcount
                if count != 1:
                    raise JobStateError("Job claim was interrupted")
                con.commit()
                return row["job_id"], json.loads(row["request_json"])
            except Exception:
                con.rollback()
                raise

    def _finish(self, job_id: str, worker_id: str, *, status: str,
                result: dict[str, Any] | None = None, error_code: str | None = None) -> None:
        now = utcnow()
        payload = json.dumps(result, allow_nan=False) if result is not None else None
        with self._connect() as con:
            changed = con.execute("""
                UPDATE fingerprint_jobs SET status=?, result_json=?, error_code=?,
                    request_json=NULL, updated_at=?, finished_at=?
                WHERE job_id=? AND status='running' AND worker_id=?
            """, (status, payload, error_code, now, now, job_id, worker_id)).rowcount
            if changed != 1:
                con.rollback()
                raise JobStateError("Cannot finish job: not owned by this worker or already finished")
            con.commit()

    def complete(self, job_id: str, worker_id: str, result: dict[str, Any]) -> None:
        self._finish(job_id, worker_id, status="completed", result=result)

    def fail(self, job_id: str, worker_id: str, *, error_code: str = "ANALYSIS_FAILED") -> None:
        # Only generic, static error codes should cross this boundary.
        if error_code not in {"ANALYSIS_FAILED", "WORKER_INTERRUPTED"}:
            raise ValueError("Unsupported public error code")
        self._finish(job_id, worker_id, status="failed", error_code=error_code)
