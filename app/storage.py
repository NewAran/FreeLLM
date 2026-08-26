from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def init(self) -> None:
        with self._lock, self._connect() as con:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_configs (
                    slug TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    priority INTEGER NOT NULL DEFAULT 100,
                    base_url_override TEXT,
                    credentials_enc TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_stats (
                    slug TEXT PRIMARY KEY,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    last_latency_ms INTEGER,
                    last_error TEXT,
                    cooldown_until INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def get_setting(self, key: str) -> str | None:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def is_setup(self) -> bool:
        return bool(self.get_setting("admin_password_hash") and self.get_setting("gateway_api_key_hash"))

    def get_provider(self, slug: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM provider_configs WHERE slug = ?", (slug,)).fetchone()
            return dict(row) if row else None

    def list_providers(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT * FROM provider_configs ORDER BY priority, slug").fetchall()
            return [dict(r) for r in rows]

    def save_provider(
        self,
        slug: str,
        enabled: bool,
        priority: int,
        base_url_override: str | None,
        credentials_enc: str | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO provider_configs(slug,enabled,priority,base_url_override,credentials_enc,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(slug) DO UPDATE SET
                    enabled=excluded.enabled,
                    priority=excluded.priority,
                    base_url_override=excluded.base_url_override,
                    credentials_enc=COALESCE(excluded.credentials_enc, provider_configs.credentials_enc),
                    updated_at=excluded.updated_at
                """,
                (slug, int(enabled), priority, base_url_override or None, credentials_enc, now),
            )

    def stats_for(self, slug: str) -> dict[str, Any]:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM provider_stats WHERE slug = ?", (slug,)).fetchone()
            if row:
                return dict(row)
            return {
                "slug": slug,
                "success_count": 0,
                "failure_count": 0,
                "last_latency_ms": None,
                "last_error": None,
                "cooldown_until": 0,
            }

    def all_stats(self) -> dict[str, dict[str, Any]]:
        with self._lock, self._connect() as con:
            return {r["slug"]: dict(r) for r in con.execute("SELECT * FROM provider_stats").fetchall()}

    def record_success(self, slug: str, latency_ms: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO provider_stats(slug,success_count,failure_count,last_latency_ms,last_error,cooldown_until,updated_at)
                VALUES(?,1,0,?,NULL,0,?)
                ON CONFLICT(slug) DO UPDATE SET
                    success_count=success_count+1,
                    last_latency_ms=excluded.last_latency_ms,
                    last_error=NULL,
                    cooldown_until=0,
                    updated_at=excluded.updated_at
                """,
                (slug, latency_ms, now),
            )

    def record_failure(self, slug: str, error: str, cooldown_until: int = 0) -> None:
        now = datetime.now(timezone.utc).isoformat()
        error = error[:800]
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO provider_stats(slug,success_count,failure_count,last_latency_ms,last_error,cooldown_until,updated_at)
                VALUES(?,0,1,NULL,?,?,?)
                ON CONFLICT(slug) DO UPDATE SET
                    failure_count=failure_count+1,
                    last_error=excluded.last_error,
                    cooldown_until=MAX(provider_stats.cooldown_until, excluded.cooldown_until),
                    updated_at=excluded.updated_at
                """,
                (slug, error, cooldown_until, now),
            )
