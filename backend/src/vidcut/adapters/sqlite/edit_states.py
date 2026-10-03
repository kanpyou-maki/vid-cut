"""EditStateRepository の SQLite 実装（楽観的排他）。編集状態は 1 レクチャー 1 行の JSON で持つ。"""

import json
import sqlite3
from dataclasses import replace

from vidcut.adapters.sqlite.database import NOW, transaction
from vidcut.domain.intervals import Interval
from vidcut.domain.models import EditState, ManualCut
from vidcut.pipeline.ports import NotFoundError, VersionConflictError


class SqliteEditStateRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, lecture_id: str) -> EditState:
        row = self._conn.execute(
            "SELECT version, restored_suggestion_ids, manual_cuts FROM edit_states"
            " WHERE lecture_id = ?",
            (lecture_id,),
        ).fetchone()
        if row is None:
            return EditState(lecture_id=lecture_id, version=0)
        return EditState(
            lecture_id=lecture_id,
            version=row["version"],
            restored_suggestion_ids=frozenset(json.loads(row["restored_suggestion_ids"])),
            manual_cuts=tuple(_to_manual_cut(cut) for cut in json.loads(row["manual_cuts"])),
        )

    def save(self, state: EditState) -> EditState:
        saved_version = state.version + 1
        values = (
            saved_version,
            json.dumps(sorted(state.restored_suggestion_ids)),
            json.dumps([_from_manual_cut(cut) for cut in state.manual_cuts], ensure_ascii=False),
        )
        with transaction(self._conn):
            if state.version == 0:
                self._insert_first(state.lecture_id, values)
            else:
                cursor = self._conn.execute(
                    "UPDATE edit_states SET version = ?, restored_suggestion_ids = ?,"
                    f" manual_cuts = ?, updated_at = {NOW} WHERE lecture_id = ? AND version = ?",
                    (*values, state.lecture_id, state.version),
                )
                if cursor.rowcount == 0:
                    raise VersionConflictError(_conflict_message(state))
        return replace(state, version=saved_version)

    def _insert_first(self, lecture_id: str, values: tuple[int, str, str]) -> None:
        exists = self._conn.execute("SELECT 1 FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
        if exists is None:
            raise NotFoundError(f"レクチャーがありません: {lecture_id}")
        cursor = self._conn.execute(
            "INSERT INTO edit_states (version, restored_suggestion_ids, manual_cuts, lecture_id)"
            " VALUES (?, ?, ?, ?) ON CONFLICT (lecture_id) DO NOTHING",
            (*values, lecture_id),
        )
        if cursor.rowcount == 0:
            raise VersionConflictError(f"編集状態は別の画面で既に保存されています: {lecture_id}")


def _conflict_message(state: EditState) -> str:
    return f"編集状態が別の画面で更新されています（版 {state.version} は古い）: {state.lecture_id}"


def _from_manual_cut(cut: ManualCut) -> dict[str, str | int]:
    return {
        "id": cut.id,
        "recording_id": cut.recording_id,
        "start_ms": cut.span.start_ms,
        "end_ms": cut.span.end_ms,
    }


def _to_manual_cut(data: dict[str, str | int]) -> ManualCut:
    return ManualCut(
        id=str(data["id"]),
        recording_id=str(data["recording_id"]),
        span=Interval(int(data["start_ms"]), int(data["end_ms"])),
    )
