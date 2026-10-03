"""RecordingRepository の SQLite 実装。"""

import sqlite3
from datetime import datetime

from vidcut.domain.models import MediaInfo, Recording

_COLUMNS = (
    "id, source_path, fingerprint, duration_ms, recorded_at,"
    " width, height, is_vfr, avg_fps, audio_rate"
)


class SqliteRecordingRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, recording: Recording) -> None:
        media = recording.media
        recorded_at = recording.recorded_at.isoformat() if recording.recorded_at else None
        try:
            self._conn.execute(
                f"INSERT INTO recordings ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    recording.id,
                    recording.source_path,
                    recording.fingerprint,
                    recording.duration_ms,
                    recorded_at,
                    media.width,
                    media.height,
                    int(media.is_vfr),
                    media.avg_fps,
                    media.audio_rate,
                ),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"この録画ファイルは既に登録されています: {recording.id}") from e

    def get(self, recording_id: str) -> Recording | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
        return _to_recording(row) if row else None

    def find_by_fingerprint(self, fingerprint: str) -> Recording | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM recordings WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        return _to_recording(row) if row else None

    def list_all(self) -> tuple[Recording, ...]:
        rows = self._conn.execute(f"SELECT {_COLUMNS} FROM recordings ORDER BY seq").fetchall()
        return tuple(_to_recording(row) for row in rows)


def _to_recording(row: sqlite3.Row) -> Recording:
    recorded_at = row["recorded_at"]
    return Recording(
        id=row["id"],
        source_path=row["source_path"],
        fingerprint=row["fingerprint"],
        duration_ms=row["duration_ms"],
        recorded_at=datetime.fromisoformat(recorded_at) if recorded_at else None,
        media=MediaInfo(
            width=row["width"],
            height=row["height"],
            is_vfr=bool(row["is_vfr"]),
            avg_fps=row["avg_fps"],
            audio_rate=row["audio_rate"],
        ),
    )
