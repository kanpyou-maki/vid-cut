import sqlite3
from pathlib import Path

from vidcut.adapters.sqlite.database import MIGRATIONS, SCHEMA_VERSION, open_database
from vidcut.adapters.sqlite.settings import SqliteSettingsRepository
from vidcut.domain.timeline import KeepPadding

PADDING = KeepPadding(before_ms=100, after_ms=300, after_sentence_ms=800)


class TestKeepPadding:
    def test_is_missing_until_saved(self, conn: sqlite3.Connection) -> None:
        assert SqliteSettingsRepository(conn).keep_padding() is None

    def test_saves_and_reads(self, conn: sqlite3.Connection) -> None:
        repo = SqliteSettingsRepository(conn)
        repo.save_keep_padding(PADDING)
        assert repo.keep_padding() == PADDING

    def test_saving_again_replaces_the_value(self, conn: sqlite3.Connection) -> None:
        repo = SqliteSettingsRepository(conn)
        repo.save_keep_padding(PADDING)
        repo.save_keep_padding(KeepPadding(0, 0, 0))
        assert repo.keep_padding() == KeepPadding(0, 0, 0)

    def test_clearing_removes_the_value(self, conn: sqlite3.Connection) -> None:
        repo = SqliteSettingsRepository(conn)
        repo.save_keep_padding(PADDING)
        repo.clear_keep_padding()
        assert repo.keep_padding() is None

    def test_clearing_without_a_value_is_fine(self, conn: sqlite3.Connection) -> None:
        SqliteSettingsRepository(conn).clear_keep_padding()

    def test_another_connection_sees_the_saved_value(self, db_path: Path) -> None:
        # API が保存した値を、worker（別の接続）が書き出しのときに読む
        writer, reader = open_database(db_path), open_database(db_path)
        try:
            SqliteSettingsRepository(writer).save_keep_padding(PADDING)
            assert SqliteSettingsRepository(reader).keep_padding() == PADDING
        finally:
            writer.close()
            reader.close()

    def test_deeply_nested_value_counts_as_missing(self, conn: sqlite3.Connection) -> None:
        # データベースを直接書き換えられても、読み取りで落ちない
        nested = "[" * 100_000 + "]" * 100_000
        conn.execute("INSERT INTO settings (key, value) VALUES ('keep_padding', ?)", (nested,))
        assert SqliteSettingsRepository(conn).keep_padding() is None

    def test_unreadable_value_counts_as_missing(self, conn: sqlite3.Connection) -> None:
        # 壊れた値で書き出しを止めない（既定値に戻る）
        for stored in (
            "{",
            "[]",
            '{"before_ms": 1}',
            '{"before_ms": -1, "after_ms": 0, "after_sentence_ms": 0}',
            '{"before_ms": 2001, "after_ms": 0, "after_sentence_ms": 0}',
            '{"before_ms": 1.5, "after_ms": 0, "after_sentence_ms": 0}',
            '{"before_ms": 0, "after_ms": 0, "after_sentence_ms": 0, "extra": 1}',
        ):
            conn.execute("DELETE FROM settings")
            conn.execute("INSERT INTO settings (key, value) VALUES ('keep_padding', ?)", (stored,))
            assert SqliteSettingsRepository(conn).keep_padding() is None, stored


class TestMigration:
    def test_adds_the_settings_table_to_an_existing_database(self, db_path: Path) -> None:
        before = SCHEMA_VERSION - 1
        old = sqlite3.connect(db_path)
        old.executescript(
            "BEGIN; " + "".join(MIGRATIONS[:before]) + f" PRAGMA user_version = {before}; COMMIT;"
        )
        old.execute("INSERT INTO lectures (id, title) VALUES ('l1', '残る')")
        old.commit()
        old.close()

        conn = open_database(db_path)
        try:
            assert SqliteSettingsRepository(conn).keep_padding() is None
            assert conn.execute("SELECT title FROM lectures").fetchone()["title"] == "残る"
        finally:
            conn.close()
