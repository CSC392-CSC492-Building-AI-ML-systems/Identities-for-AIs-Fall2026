"""Separate SQLite job worker for mock or authenticated live jobs.

From Git Bash in the GitHub repository root:
    python -m system.backend.worker --once
    python -m system.backend.worker --loop --poll-seconds 1

Live mode requires a shared SYSTEM_JOB_FERNET_KEY and a locally provisioned
auth token file; it can make real billable provider calls. Judge stays mocked.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .jobs.runner import MockJobWorker
from .jobs.store import SqliteJobStore
from .jobs.live_store import SqliteLiveJobStore
from .jobs.live_runner import LiveJobWorker
from .security.crypto import LiveCrypto, FileSecretVault
from .services.analysis import make_mock_gateway
from .services.live import LiveOpenAIAnalysisGateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Process at most one queued job and exit")
    mode.add_argument("--loop", action="store_true", help="Keep polling until Ctrl+C")
    parser.add_argument("--kind", choices=("mock", "live"), default="mock")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--db-path", type=Path, default=None,
                        help="SQLite file (default: SYSTEM_JOB_DB_PATH or system/.local/jobs.sqlite3)")
    args = parser.parse_args(argv)
    if not (0.1 <= args.poll_seconds <= 60.0):
        parser.error("--poll-seconds must be between 0.1 and 60")
    db_path = args.db_path or os.environ.get('SYSTEM_JOB_DB_PATH')
    if args.kind == 'live':
        crypto = LiveCrypto.from_env()
        if crypto is None:
            parser.error('Live worker requires SYSTEM_JOB_FERNET_KEY shared with API process')
        store = SqliteLiveJobStore(crypto, db_path)
        gateway = LiveOpenAIAnalysisGateway(make_mock_gateway().workflow)
        worker = LiveJobWorker(store, FileSecretVault(crypto), gateway)
    else:
        store = SqliteJobStore(db_path)
        worker = MockJobWorker(store)
    try:
        while True:
            job_id = worker.run_once()
            if job_id:
                print(f"Processed {args.kind} job: {job_id}", flush=True)
            if args.once:
                if job_id is None:
                    print("No queued jobs", flush=True)
                return 0
            if job_id is None:
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("Worker stopped", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
