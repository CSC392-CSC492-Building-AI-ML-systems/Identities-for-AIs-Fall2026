"""Generate a LOCAL-ONLY Fernet key file for M4 API/worker development.

Run once: python -m system.backend.security.setup_dev_crypto
Both Git Bash terminals: export SYSTEM_JOB_FERNET_KEY="$(cat system/.local/dev_job.key)"

WARNING: the key is stored on disk close to encrypted data for convenience.
This is not a production vault or production-grade key management.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from cryptography.fernet import Fernet

DEFAULT = Path(__file__).resolve().parents[2] / '.local' / 'dev_job.key'


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--file', type=Path, default=DEFAULT)
    args = p.parse_args(argv)
    path=args.file.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd=os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f'Existing key preserved: {path}')
        return 0
    with os.fdopen(fd, 'wb') as f:
        f.write(Fernet.generate_key())
    print(f'Development encryption key written: {path}')
    print('Do NOT commit or share this file. Production requires managed key storage.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
