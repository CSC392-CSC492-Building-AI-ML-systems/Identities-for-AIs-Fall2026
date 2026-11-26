"""Owner-scoped deployment/baseline history; NO credentials and NO auto-promotion.

SQLite is for the existing local-development backend. Baseline snapshots record
human-asserted, manually reviewed identities, not ML classifier guarantees.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4
from typing import Any

from .jobs.store import SqliteJobStore, utcnow
from .cards_repository import field_changes


class NotFound(Exception):
    pass


class HistoryStore(SqliteJobStore):
    def initialize(self):
        super().initialize()
        with self._connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS monitored_deployments (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, label TEXT NOT NULL,
                provider TEXT NOT NULL, requested_model_id TEXT NOT NULL,
                created_at TEXT NOT NULL)''')
            con.execute('''CREATE TABLE IF NOT EXISTS confirmed_baselines (
                id TEXT PRIMARY KEY, deployment_id TEXT NOT NULL,
                revision INTEGER NOT NULL, model_id TEXT NOT NULL,
                confirmation_source TEXT NOT NULL, review_note TEXT NOT NULL,
                confirmed_at TEXT NOT NULL, card_snapshot_json TEXT,
                card_snapshot_sha256 TEXT, card_status TEXT NOT NULL,
                FOREIGN KEY(deployment_id) REFERENCES monitored_deployments(id),
                UNIQUE(deployment_id, revision))''')
            con.execute('CREATE INDEX IF NOT EXISTS idx_deployments_owner ON monitored_deployments(owner_id)')
            con.commit()

    def create_deployment(self, owner_id: str, label: str, provider: str, requested_model_id: str) -> dict:
        identifier, now = str(uuid4()), utcnow()
        with self._connect() as con:
            con.execute('INSERT INTO monitored_deployments VALUES (?,?,?,?,?,?)',
                        (identifier, owner_id, label, provider, requested_model_id, now))
            con.commit()
        return {'id': identifier, 'label': label, 'provider': provider,
                'requested_model_id': requested_model_id, 'created_at': now,
                'baseline': None}

    def get_deployment(self, owner_id: str, deployment_id: str) -> dict:
        with self._connect() as con:
            row = con.execute('SELECT * FROM monitored_deployments WHERE id=? AND owner_id=?',
                              (deployment_id, owner_id)).fetchone()
        if row is None:
            raise NotFound('Deployment not found')
        return {'id': row['id'], 'label': row['label'], 'provider': row['provider'],
                'requested_model_id': row['requested_model_id'], 'created_at': row['created_at'],
                'baseline': self.latest_baseline(owner_id, deployment_id)}

    def list_deployments(self, owner_id: str) -> list[dict]:
        with self._connect() as con:
            rows = con.execute('SELECT id FROM monitored_deployments WHERE owner_id=? ORDER BY created_at,id',
                               (owner_id,)).fetchall()
        return [self.get_deployment(owner_id, r['id']) for r in rows]

    @staticmethod
    def _baseline(row: sqlite3.Row) -> dict[str, Any]:
        return {'id': row['id'], 'revision': row['revision'], 'model_id': row['model_id'],
                'confirmation_source': row['confirmation_source'],
                'review_note': row['review_note'], 'confirmed_at': row['confirmed_at'],
                'card_status': row['card_status'],
                'card_snapshot_sha256': row['card_snapshot_sha256'],
                'card_snapshot': json.loads(row['card_snapshot_json']) if row['card_snapshot_json'] else None}

    def list_history(self, owner_id: str, deployment_id: str) -> list[dict]:
        self._require_owner(owner_id, deployment_id)
        with self._connect() as con:
            rows = con.execute('''SELECT b.* FROM confirmed_baselines b WHERE deployment_id=?
                                ORDER BY revision ASC''', (deployment_id,)).fetchall()
        return [self._baseline(row) for row in rows]

    def _require_owner(self, owner_id: str, deployment_id: str) -> None:
        with self._connect() as con:
            row = con.execute('SELECT 1 FROM monitored_deployments WHERE id=? AND owner_id=?',
                              (deployment_id, owner_id)).fetchone()
        if row is None:
            raise NotFound('Deployment not found')

    def latest_baseline(self, owner_id: str, deployment_id: str) -> dict | None:
        self._require_owner(owner_id, deployment_id)
        with self._connect() as con:
            row = con.execute('''SELECT * FROM confirmed_baselines WHERE deployment_id=?
                             ORDER BY revision DESC LIMIT 1''', (deployment_id,)).fetchone()
        return self._baseline(row) if row else None

    def record_reviewed_baseline(self, owner_id: str, deployment_id: str, model_id: str,
                                 review_note: str, card_snapshot: dict | None) -> dict:
        # Only manually reviewed entries may be recorded via this method.
        self._require_owner(owner_id, deployment_id)
        payload = (json.dumps(card_snapshot, sort_keys=True, ensure_ascii=False,
                              separators=(',', ':')) if card_snapshot is not None else None)
        digest = hashlib.sha256(payload.encode()).hexdigest() if payload is not None else None
        now, identifier = utcnow(), str(uuid4())
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT 1 FROM monitored_deployments WHERE id=? AND owner_id=?',
                              (deployment_id, owner_id)).fetchone()
            if row is None:
                con.rollback()
                raise NotFound('Deployment not found')
            prev = con.execute('SELECT COALESCE(MAX(revision),0) AS rev FROM confirmed_baselines WHERE deployment_id=?',
                               (deployment_id,)).fetchone()
            revision = prev['rev'] + 1
            con.execute('''INSERT INTO confirmed_baselines
              (id,deployment_id,revision,model_id,confirmation_source,review_note,confirmed_at,
               card_snapshot_json,card_snapshot_sha256,card_status)
               VALUES (?,?,?,?,?,?,?,?,?,?)''',
               (identifier, deployment_id, revision, model_id, 'manual_review', review_note,
                now, payload, digest, 'available' if payload else 'unavailable'))
            con.commit()
        return self.latest_baseline(owner_id, deployment_id)

    def changes(self, owner_id: str, deployment_id: str) -> dict:
        history = self.list_history(owner_id, deployment_id)
        if not history:
            return {'status': 'no_baseline', 'before_model_id': None, 'after_model_id': None,
                    'identity_change': None, 'card_comparison': {'status':'not_comparable','changes':[]}}
        after = history[-1]
        if len(history) == 1:
            return {'status': 'no_previous_baseline', 'before_model_id': None,
                    'after_model_id': after['model_id'], 'identity_change': None,
                    'card_comparison': {'status':'not_comparable','changes':[]}}
        before = history[-2]
        return {'status': 'manual_reviewed_comparison', 'before_model_id': before['model_id'],
                'after_model_id': after['model_id'],
                'before_confirmed_at': before['confirmed_at'], 'after_confirmed_at': after['confirmed_at'],
                'before_revision': before['revision'], 'after_revision': after['revision'],
                'identity_change': before['model_id'] != after['model_id'],
                'card_comparison': field_changes(before['card_snapshot'], after['card_snapshot'])}
