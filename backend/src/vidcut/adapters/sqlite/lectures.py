"""LectureRepository の SQLite 実装。1 本の録画ファイルは高々 1 つのレクチャーに属する。"""

import sqlite3
from collections.abc import Iterable

from vidcut.adapters.sqlite.database import transaction
from vidcut.domain.models import Lecture


class SqliteLectureRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, lecture_id: str) -> Lecture | None:
        row = self._conn.execute(
            "SELECT id, title FROM lectures WHERE id = ?", (lecture_id,)
        ).fetchone()
        return self._to_lecture(row) if row else None

    def find_by_recording(self, recording_id: str) -> Lecture | None:
        row = self._conn.execute(
            "SELECT lecture_id FROM lecture_recordings WHERE recording_id = ?", (recording_id,)
        ).fetchone()
        return self.get(row["lecture_id"]) if row else None

    def list_all(self) -> tuple[Lecture, ...]:
        rows = self._conn.execute("SELECT id, title FROM lectures ORDER BY seq").fetchall()
        return tuple(self._to_lecture(row) for row in rows)

    def save(self, lecture: Lecture) -> None:
        self.replace(remove=(), save=(lecture,))

    def delete(self, lecture_id: str) -> None:
        self.replace(remove=(lecture_id,), save=())

    def replace(self, *, remove: Iterable[str], save: Iterable[Lecture]) -> None:
        with transaction(self._conn):
            for lecture_id in remove:
                self._conn.execute("DELETE FROM lectures WHERE id = ?", (lecture_id,))
            lectures = tuple(save)
            # 録画ファイルの付け替えで一意制約に当たらないよう、先にすべての構成を外す
            for lecture in lectures:
                self._conn.execute(
                    "DELETE FROM lecture_recordings WHERE lecture_id = ?", (lecture.id,)
                )
            for lecture in lectures:
                self._write(lecture)

    def _write(self, lecture: Lecture) -> None:
        self._conn.execute(
            "INSERT INTO lectures (id, title) VALUES (?, ?)"
            " ON CONFLICT (id) DO UPDATE SET title = excluded.title",
            (lecture.id, lecture.title),
        )
        try:
            self._conn.executemany(
                "INSERT INTO lecture_recordings (lecture_id, position, recording_id)"
                " VALUES (?, ?, ?)",
                [(lecture.id, pos, rid) for pos, rid in enumerate(lecture.recording_ids)],
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"録画ファイルが未登録か、別のレクチャーに属しています: {lecture.recording_ids}"
            ) from e

    def _to_lecture(self, row: sqlite3.Row) -> Lecture:
        recording_rows = self._conn.execute(
            "SELECT recording_id FROM lecture_recordings WHERE lecture_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        return Lecture(
            id=row["id"],
            title=row["title"],
            recording_ids=tuple(r["recording_id"] for r in recording_rows),
        )
