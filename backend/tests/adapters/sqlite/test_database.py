import sqlite3
from pathlib import Path

import pytest

from vidcut.adapters.sqlite.database import SCHEMA_VERSION, open_database, transaction


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


class TestOpenDatabase:
    def test_creates_schema_and_parent_directory(self, tmp_path: Path) -> None:
        conn = open_database(tmp_path / "nested" / "vidcut.sqlite3")
        assert {"recordings", "lectures", "lecture_recordings", "edit_states", "jobs"} <= tables(
            conn
        )
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    def test_enables_foreign_keys_wal_and_busy_timeout(self, conn: sqlite3.Connection) -> None:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 1000

    def test_reopening_keeps_data(self, db_path: Path) -> None:
        first = open_database(db_path)
        first.execute("INSERT INTO lectures (id, title) VALUES ('l1', 't')")
        first.close()
        second = open_database(db_path)
        assert second.execute("SELECT count(*) FROM lectures").fetchone()[0] == 1

    def test_refuses_database_from_newer_version(self, db_path: Path) -> None:
        conn = open_database(db_path)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        conn.close()
        with pytest.raises(RuntimeError, match="新しい"):
            open_database(db_path)


class TestTransaction:
    def test_commits_on_success(self, conn: sqlite3.Connection) -> None:
        with transaction(conn):
            conn.execute("INSERT INTO lectures (id, title) VALUES ('l1', 't')")
        assert conn.execute("SELECT count(*) FROM lectures").fetchone()[0] == 1

    def test_rolls_back_on_error(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(ValueError), transaction(conn):
            conn.execute("INSERT INTO lectures (id, title) VALUES ('l1', 't')")
            raise ValueError("boom")
        assert conn.execute("SELECT count(*) FROM lectures").fetchone()[0] == 0

    def test_failed_commit_leaves_connection_usable(self, conn: sqlite3.Connection) -> None:
        # 外部キーの検査を COMMIT まで遅らせ、COMMIT 自体を失敗させる
        conn.execute("PRAGMA defer_foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError), transaction(conn):
            conn.execute(
                "INSERT INTO lecture_recordings (lecture_id, position, recording_id)"
                " VALUES ('missing', 0, 'missing')"
            )
        assert not conn.in_transaction
        with transaction(conn):
            conn.execute("INSERT INTO lectures (id, title) VALUES ('l1', 't')")
        assert conn.execute("SELECT count(*) FROM lectures").fetchone()[0] == 1
