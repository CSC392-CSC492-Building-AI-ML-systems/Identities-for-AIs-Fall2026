"""Separate local SQLite job worker.

From Git Bash in the GitHub repository root:
    python -m system.backend.worker --once
    python -m system.backend.worker --loop --poll-seconds 1

Mock only; no user keys, live target calls or external judge. Never expose the
unauthenticated development API or SQLite data to untrusted users.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .jobs.runner import MockJobWorker
from .jobs.store import SqliteJobStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Process at most one queued mock job and exit")
    mode.add_argument("--loop", action="store_true", help="Keep polling until Ctrl+C")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--db-path", type=Path, default=None,
                        help="SQLite file (default: SYSTEM_JOB_DB_PATH or system/.local/jobs.sqlite3)")
    args = parser.parse_args(argv)
    if not (0.1 <= args.poll_seconds <= 60.0):
        parser.error("--poll-seconds must be between 0.1 and 60")
    store = SqliteJobStore(args.db_path or os.environ.get("SYSTEM_JOB_DB_PATH"))
    worker = MockJobWorker(store)
    try:
        while True:
            job_id = worker.run_once()
            if job_id:
                print(f"Processed mock job: {job_id}", flush=True)
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
