"""Local encrypted payloads and one-time worker secret files.

The job table NEVER contains raw provider API keys; only an opaque reference.
The worker and API processes must share SYSTEM_JOB_FERNET_KEY via environment.
Encrypted temporary files are only a local educational substitute for a managed
short-lived secret broker. Filesystem admins/key holders remain trusted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

SYSTEM_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VAULT_DIR = SYSTEM_ROOT / '.local' / 'live_secrets'


class LiveCrypto:
    def __init__(self, key: str | bytes):
        self._cipher = Fernet(key.encode('ascii') if isinstance(key, str) else key)

    @classmethod
    def from_env(cls) -> 'LiveCrypto | None':
        key = os.environ.get('SYSTEM_JOB_FERNET_KEY')
        return cls(key) if key else None

    def seal(self, data: dict) -> str:
        return self._cipher.encrypt(json.dumps(data, allow_nan=False).encode('utf-8')).decode('ascii')

    def open(self, token: str) -> dict:
        try:
            data = json.loads(self._cipher.decrypt(token.encode('ascii')))
        except (InvalidToken, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError('Encrypted job payload unavailable or invalid') from None
        if not isinstance(data, dict):
            raise ValueError('Encrypted job payload invalid')
        return data


class FileSecretVault:
    def __init__(self, crypto: LiveCrypto, folder: str | Path | None = None):
        self.crypto = crypto
        self.folder = Path(folder or os.environ.get('SYSTEM_SECRET_VAULT_DIR') or DEFAULT_VAULT_DIR).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)

    def _file(self, job_id: str) -> Path:
        try:
            value = UUID(job_id)
            if str(value) != job_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Invalid credential reference') from None
        return self.folder / f'{job_id}.secret'

    def put(self, job_id: str, owner_id: str, api_key: str) -> None:
        payload = self.crypto.seal({'owner_id': owner_id, 'api_key': api_key})
        path = self._file(job_id)
        # Exclusive create prevents accidental overwrite; mode is best effort on Windows.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='ascii') as f:
                f.write(payload)
        except BaseException:
            self.delete(job_id)
            raise

    def read(self, job_id: str, owner_id: str) -> str:
        payload = self.crypto.open(self._file(job_id).read_text(encoding='ascii'))
        if payload.get('owner_id') != owner_id or not isinstance(payload.get('api_key'), str):
            raise ValueError('Credential owner mismatch')
        return payload['api_key']

    def delete(self, job_id: str) -> None:
        self._file(job_id).unlink(missing_ok=True)
