"""接続の作成とスキーマの移行。"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
"""SQL 内で使う現在時刻（UTC、ISO 8601）。"""

_BUSY_TIMEOUT_MS = 5000

# 版ごとのスキーマ変更。追加だけを行い、既存の要素は書き換えない（PRAGMA user_version で管理）
MIGRATIONS: tuple[str, ...] = (
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
    f"""
    CREATE TABLE judgements (
        lecture_id TEXT PRIMARY KEY REFERENCES lectures (id) ON DELETE CASCADE,
        input_key TEXT NOT NULL,
        suggestions TEXT NOT NULL,
        dropped_restored_ids TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT ({NOW})
    );
    """,
    # 失敗の種別（Design Doc 3-5-2）。これより前に失敗したジョブは NULL のまま
    """
    ALTER TABLE jobs ADD COLUMN error_code TEXT;
    """,
)

SCHEMA_VERSION = len(MIGRATIONS)


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
    """囲んだ文をまとめて確定する。例外が出たらすべて取り消す。

    既にトランザクションの中なら、それに加わる（確定と取り消しはいちばん外側が行う）。
    複数のリポジトリにまたがる保存を、services が 1 つにまとめるために使う（ports の Atomic）。
    接続は同時に 1 つのスレッドからだけ使うこと。複数のスレッドで共有すると、
    別のスレッドの文がこのトランザクションに混ざる
    （API はリクエストごとに接続を開く。Design Doc 3-5-2）。
    """
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        # COMMIT 自体の失敗（外部キーの遅延検査・SQLITE_BUSY）でもトランザクションを残さない
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _migrate(conn: sqlite3.Connection) -> None:
    current: int = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"データベースがこの vid-cut より新しい版（{current}）です。vid-cut を更新してください"
        )
    for version in range(current, SCHEMA_VERSION):
        conn.executescript(
            f"BEGIN IMMEDIATE; {MIGRATIONS[version]} PRAGMA user_version = {version + 1}; COMMIT;"
        )
