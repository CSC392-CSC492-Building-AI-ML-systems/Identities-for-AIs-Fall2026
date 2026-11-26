"""Provision an M4 local development bearer token (prints it ONE time).

From repository root: python -m system.backend.security.setup_dev_auth --user alice
The generated file stores only SHA-256 digests. Never commit bearer tokens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path

from .auth import DEFAULT_AUTH_FILE, LocalTokenAuth, _USER_RE


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--user', required=True)
    p.add_argument('--file', type=Path, default=DEFAULT_AUTH_FILE)
    args = p.parse_args(argv)
    if not _USER_RE.fullmatch(args.user):
        p.error('user must contain only letters, numbers, underscore or hyphen (max 64)')
    token = secrets.token_urlsafe(32)
    path = args.file.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    users = {}
    if path.exists():
        users = LocalTokenAuth.from_file(path)._user_hashes
    users[args.user] = hashlib.sha256(token.encode('utf-8')).hexdigest()
    tmp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'users': users}, f, indent=2)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    print(f'Development token for {args.user} (shown only once):\n{token}')
    print(f'Token digest saved to: {path}')
    print('Never commit, screenshot or log this token. Re-running rotates this user token.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
