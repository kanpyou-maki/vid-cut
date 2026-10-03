"""接続の作成とスキーマの移行。"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
"""SQL 内で使う現在時刻（UTC、ISO 8601）。"""

_BUSY_TIMEOUT_MS = 5000

# 版ごとのスキーマ変更。追加だけを行い、既存の要素は書き換えない（PRAGMA user_version で管理）
_MIGRATIONS: tuple[str, ...] = (
    f"""
    CREATE TABLE recordings (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        source_path TEXT NOT NULL,
        fingerprint TEXT NOT NULL UNIQUE,
        duration_ms INTEGER NOT NULL,
        recorded_at TEXT,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        is_vfr INTEGER NOT NULL,
        avg_fps REAL NOT NULL,
        audio_rate INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT ({NOW})
    );
    CREATE TABLE lectures (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT ({NOW})
    );
    CREATE TABLE lecture_recordings (
        lecture_id TEXT NOT NULL REFERENCES lectures (id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        recording_id TEXT NOT NULL UNIQUE REFERENCES recordings (id),
        PRIMARY KEY (lecture_id, position)
    );
    CREATE TABLE edit_states (
        lecture_id TEXT PRIMARY KEY REFERENCES lectures (id) ON DELETE CASCADE,
        version INTEGER NOT NULL,
        restored_suggestion_ids TEXT NOT NULL,
        manual_cuts TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT ({NOW})
    );
    CREATE TABLE jobs (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL,
        target_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
        priority INTEGER NOT NULL,
        stage TEXT,
        progress REAL NOT NULL DEFAULT 0,
        error TEXT,
        created_at TEXT NOT NULL DEFAULT ({NOW}),
        updated_at TEXT NOT NULL DEFAULT ({NOW})
    );
    CREATE INDEX jobs_by_queue_order ON jobs (status, priority DESC, seq);
    """,
)

SCHEMA_VERSION = len(_MIGRATIONS)


def open_database(path: Path) -> sqlite3.Connection:
    """データベースを開き（なければ作り）、スキーマを最新にする。

    自動コミットで開く。複数の文をまとめるときは transaction() を使う。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")
        _migrate(conn)
    except Exception:
        conn.close()
        raise
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _migrate(conn: sqlite3.Connection) -> None:
    current: int = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"データベースがこの vid-cut より新しい版（{current}）です。vid-cut を更新してください"
        )
    for version in range(current, SCHEMA_VERSION):
        conn.executescript(
            f"BEGIN IMMEDIATE; {_MIGRATIONS[version]} PRAGMA user_version = {version + 1}; COMMIT;"
        )
