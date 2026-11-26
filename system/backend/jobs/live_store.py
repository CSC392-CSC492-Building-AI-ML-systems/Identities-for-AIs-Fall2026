"""Encrypted, owner-scoped SQLite live jobs with bounded queue lifetime.

Only prompts/model routing metadata and sanitized results are stored as
Fernet ciphertext. Provider credentials live in FileSecretVault, NOT SQLite.
No automatic retries: an interrupted billable job stays running until a
separate, explicitly approved recovery policy is implemented.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..security.crypto import LiveCrypto
from .store import JobStateError, SqliteJobStore, utcnow


class SqliteLiveJobStore(SqliteJobStore):
    def __init__(self, crypto: LiveCrypto, db_path: Path | str | None = None, *, ttl_seconds: int = 600):
        if not isinstance(ttl_seconds, int) or not 60 <= ttl_seconds <= 3600:
            raise ValueError('Queue lifetime must be 60-3600 seconds')
        self.crypto = crypto
        self.ttl_seconds = ttl_seconds
        super().__init__(db_path)

    def initialize(self) -> None:
        super().initialize()
        with self._connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS fingerprint_live_jobs (
                job_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                request_ciphertext TEXT,
                result_ciphertext TEXT,
                error_code TEXT,
                worker_id TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0
            )''')
            # Idempotent, additive migration for M4 SQLite databases.
            columns = {r['name'] for r in con.execute('PRAGMA table_info(fingerprint_live_jobs)')}
            for name, sql_type in (
                ('deployment_id', 'TEXT'), ('baseline_id', 'TEXT'),
                ('baseline_revision', 'INTEGER')):
                if name not in columns:
                    con.execute(f'ALTER TABLE fingerprint_live_jobs ADD COLUMN {name} {sql_type}')
            con.execute('CREATE INDEX IF NOT EXISTS idx_live_jobs_deployment_owner '
                        'ON fingerprint_live_jobs(owner_id,deployment_id,created_at)')
            con.execute('CREATE INDEX IF NOT EXISTS idx_live_jobs_pending ON fingerprint_live_jobs(status,created_at)')
            con.commit()

    def enqueue(self, owner_id: str, prompt: str, target_model: str, *, job_id: str,
                deployment_id: str | None = None, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utcnow()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)).isoformat(timespec='milliseconds')
        # Pin the already-owner-validated baseline to this run, not the latest
        # mutable deployment state at worker execution time.
        ciphertext = self.crypto.seal({'prompt_text': prompt, 'target_model': target_model,
                                       'deployment_id': deployment_id, 'baseline': baseline})
        with self._connect() as con:
            con.execute('''INSERT INTO fingerprint_live_jobs
               (job_id,owner_id,status,created_at,updated_at,expires_at,request_ciphertext,
                deployment_id,baseline_id,baseline_revision)
               VALUES (?,?,'queued',?,?,?,?,?,?,?)''',
                (job_id,owner_id,now,now,expires,ciphertext,deployment_id,
                 baseline['id'] if baseline else None,
                 baseline['revision'] if baseline else None))
            con.commit()
        return {'job_id':job_id,'status':'queued','mode':'live_target_mock_judge',
                'created_at':now,'deployment_id':deployment_id,
                'baseline_revision':baseline['revision'] if baseline else None}

    def get_for_owner(self, job_id: str, owner_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute('SELECT * FROM fingerprint_live_jobs WHERE job_id=? AND owner_id=?',
                              (job_id,owner_id)).fetchone()
        if row is None:
            return None
        return {
            'schema_version':'1.0', 'job_id':row['job_id'], 'mode':'live_target_mock_judge',
            'status':row['status'], 'created_at':row['created_at'], 'updated_at':row['updated_at'],
            'started_at':row['started_at'], 'finished_at':row['finished_at'],
            'attempt_count':row['attempt_count'], 'error_code':row['error_code'],
            'deployment_id':row['deployment_id'], 'baseline_revision':row['baseline_revision'],
            'result': self.crypto.open(row['result_ciphertext']) if row['result_ciphertext'] else None,
        }

    def list_for_deployment(self, owner_id: str, deployment_id: str) -> list[dict[str, Any]]:
        """Owner-scoped job index, no encrypted prompts, keys or raw reports."""
        with self._connect() as con:
            rows = con.execute("""SELECT job_id,status,created_at,updated_at,
                 baseline_revision,error_code FROM fingerprint_live_jobs
                 WHERE owner_id=? AND deployment_id=? ORDER BY created_at DESC,job_id DESC""",
                 (owner_id,deployment_id)).fetchall()
        return [{'job_id':row['job_id'], 'status':row['status'],
                 'created_at':row['created_at'], 'updated_at':row['updated_at'],
                 'baseline_revision':row['baseline_revision'],
                 'error_code':row['error_code']} for row in rows]

    def expire_queued(self) -> list[str]:
        """Mark queued jobs expired. The worker deletes the associated secrets."""
        now = utcnow()
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            rows = con.execute("SELECT job_id FROM fingerprint_live_jobs WHERE status='queued' AND expires_at<=?",(now,)).fetchall()
            ids = [r['job_id'] for r in rows]
            if ids:
                con.executemany('''UPDATE fingerprint_live_jobs SET status='failed',
                    error_code='JOB_EXPIRED', request_ciphertext=NULL, updated_at=?, finished_at=?
                    WHERE job_id=? AND status='queued' ''', [(now,now,j) for j in ids])
            con.commit()
        return ids

    def expire_abandoned_running(self, *, max_running_seconds: int = 900) -> list[str]:
        """Fail stale running jobs without retrying possibly billable calls.

        This is a local cleanup policy, NOT a full worker lease/heartbeat.
        An unusually slow legitimate job could be marked abandoned.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_running_seconds)).isoformat(timespec='milliseconds')
        now = utcnow()
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            rows = con.execute("""SELECT job_id FROM fingerprint_live_jobs WHERE status='running'
                AND started_at<=?""", (cutoff,)).fetchall()
            ids = [r['job_id'] for r in rows]
            if ids:
                con.executemany("""UPDATE fingerprint_live_jobs SET status='failed',
                    error_code='WORKER_INTERRUPTED', request_ciphertext=NULL,
                    updated_at=?,finished_at=? WHERE job_id=? AND status='running' """,
                    [(now,now,job_id) for job_id in ids])
            con.commit()
        return ids

    def claim_next(self, worker_id: str) -> tuple[str,str,dict[str,Any]] | None:
        if not worker_id or len(worker_id)>128:
            raise ValueError('Invalid worker ID')
        with self._connect() as con:
            try:
                con.execute('BEGIN IMMEDIATE')
                row=con.execute("""SELECT job_id,owner_id,request_ciphertext FROM fingerprint_live_jobs
                  WHERE status='queued' AND expires_at>? ORDER BY created_at,rowid LIMIT 1""",(utcnow(),)).fetchone()
                if row is None:
                    con.commit()
                    return None
                now=utcnow()
                count=con.execute('''UPDATE fingerprint_live_jobs SET status='running',
                    worker_id=?,updated_at=?,started_at=?,attempt_count=attempt_count+1
                    WHERE job_id=? AND status='queued' ''',(worker_id,now,now,row['job_id'])).rowcount
                if count!=1: raise JobStateError('Concurrent job claim')
                con.commit()
                return row['job_id'],row['owner_id'],self.crypto.open(row['request_ciphertext'])
            except Exception:
                con.rollback()
                raise

    def finish(self, job_id: str, worker_id: str, *, result: dict | None=None,
               error_code: str | None=None) -> None:
        if (result is None)==(error_code is None):
            raise ValueError('Provide result XOR error_code')
        if error_code is not None and error_code not in {'ANALYSIS_FAILED','PROVIDER_ERROR','CREDENTIAL_UNAVAILABLE'}:
            raise ValueError('Invalid public error code')
        status='completed' if result is not None else 'failed'
        encrypted=self.crypto.seal(result) if result is not None else None
        now=utcnow()
        with self._connect() as con:
            changed=con.execute('''UPDATE fingerprint_live_jobs SET status=?,result_ciphertext=?,
              error_code=?,request_ciphertext=NULL,updated_at=?,finished_at=?
              WHERE job_id=? AND worker_id=? AND status='running' ''',
              (status,encrypted,error_code,now,now,job_id,worker_id)).rowcount
            if changed!=1:
                con.rollback()
                raise JobStateError('Live job not owned by this worker')
            con.commit()
