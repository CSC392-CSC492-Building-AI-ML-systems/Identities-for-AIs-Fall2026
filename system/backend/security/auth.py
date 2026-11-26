"""High-entropy bearer-token authentication for the local M4 prototype.

The on-disk user file contains only SHA-256 digests of randomly generated
256-bit tokens. This is NOT a replacement for production OIDC/login, rotation,
rate limits, HTTPS or a user-management service.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import Depends

SYSTEM_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTH_FILE = SYSTEM_ROOT / '.local' / 'dev_users.json'
_auth_header = HTTPBearer(auto_error=False)
_USER_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


class LocalTokenAuth:
    def __init__(self, user_hashes: dict[str, str]):
        if not user_hashes:
            raise ValueError('At least one user must be provisioned')
        for user, digest in user_hashes.items():
            if not _USER_RE.fullmatch(user) or not re.fullmatch(r'[a-f0-9]{64}', digest):
                raise ValueError('Invalid user ID or token digest')
        if len(set(user_hashes.values())) != len(user_hashes):
            raise ValueError('Duplicate token digests')
        self._user_hashes = user_hashes.copy()

    @classmethod
    def from_file(cls, path: Path | str) -> 'LocalTokenAuth':
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or set(data) != {'users'} or not isinstance(data['users'], dict):
            raise ValueError('Invalid development auth file')
        return cls(data['users'])

    def user_for_token(self, token: str) -> str | None:
        if not token or len(token) > 1024:
            return None
        candidate = hashlib.sha256(token.encode('utf-8')).hexdigest()
        found = None
        for user, digest in self._user_hashes.items():
            if hmac.compare_digest(candidate, digest):
                found = user
        return found


def default_auth() -> LocalTokenAuth | None:
    path = Path(os.environ.get('SYSTEM_DEV_AUTH_FILE', DEFAULT_AUTH_FILE))
    return LocalTokenAuth.from_file(path) if path.is_file() else None


def require_user(request: Request, authorization: HTTPAuthorizationCredentials | None = Depends(_auth_header)) -> str:
    auth: LocalTokenAuth | None = getattr(request.app.state, 'token_auth', None)
    if auth is None:
        raise HTTPException(status_code=503, detail='Authenticated live jobs are not configured')
    user = auth.user_for_token(authorization.credentials) if authorization and authorization.scheme.lower() == 'bearer' else None
    if user is None:
        raise HTTPException(status_code=401, detail='Invalid or missing bearer token',
                            headers={'WWW-Authenticate': 'Bearer'})
    return user
