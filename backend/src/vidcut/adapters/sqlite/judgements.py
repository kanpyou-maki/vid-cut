"""JudgementRepository の SQLite 実装。判定結果は 1 レクチャー 1 行の JSON で持つ。

レクチャーを消すと（まとめる・解除）、判定結果も一緒に消える。
"""

import json
import sqlite3
from typing import Any

from vidcut.adapters.sqlite.database import NOW, transaction
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion
from vidcut.pipeline.ports import Judgement, NotFoundError


class SqliteJudgementRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, lecture_id: str) -> Judgement | None:
        row = self._conn.execute(
            "SELECT input_key, suggestions, dropped_restored_ids FROM judgements"
            " WHERE lecture_id = ?",
            (lecture_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            return Judgement(
                lecture_id=lecture_id,
                input_key=row["input_key"],
                suggestions=tuple(_to_suggestion(s) for s in json.loads(row["suggestions"])),
                dropped_restored_ids=tuple(str(i) for i in json.loads(row["dropped_restored_ids"])),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"保存された判定結果の形が不正です（{lecture_id}）: {e}") from e

    def save(self, judgement: Judgement) -> None:
        try:
            self._conn.execute(
                "INSERT INTO judgements (lecture_id, input_key, suggestions, dropped_restored_ids)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT (lecture_id) DO UPDATE SET input_key = excluded.input_key,"
                " suggestions = excluded.suggestions,"
                f" dropped_restored_ids = excluded.dropped_restored_ids, updated_at = {NOW}",
                (
                    judgement.lecture_id,
                    judgement.input_key,
                    json.dumps(
                        [_from_suggestion(s) for s in judgement.suggestions], ensure_ascii=False
                    ),
                    json.dumps(list(judgement.dropped_restored_ids)),
                ),
            )
        except sqlite3.IntegrityError as e:
            raise NotFoundError(f"レクチャーがありません: {judgement.lecture_id}") from e

    def dismiss_dropped(self, lecture_id: str, ids: frozenset[str]) -> tuple[str, ...]:
        # 判定結果の本体（input_key・suggestions）には触れず、記録の列だけを書き換える
        with transaction(self._conn):
            row = self._conn.execute(
                "SELECT dropped_restored_ids FROM judgements WHERE lecture_id = ?", (lecture_id,)
            ).fetchone()
            if row is None:
                return ()
            try:
                recorded = tuple(str(i) for i in json.loads(row["dropped_restored_ids"]))
            except (TypeError, ValueError) as e:
                raise ValueError(f"保存された判定結果の形が不正です（{lecture_id}）: {e}") from e
            remaining = tuple(i for i in recorded if i not in ids)
            if remaining != recorded:
                self._conn.execute(
                    f"UPDATE judgements SET dropped_restored_ids = ?, updated_at = {NOW}"
                    " WHERE lecture_id = ?",
                    (json.dumps(list(remaining)), lecture_id),
                )
            return remaining


def _from_suggestion(suggestion: CutSuggestion) -> dict[str, str | int | None]:
    return {
        "id": suggestion.id,
        "recording_id": suggestion.recording_id,
        "start_ms": suggestion.span.start_ms,
        "end_ms": suggestion.span.end_ms,
        "kind": suggestion.kind.value,
        "reason": suggestion.reason,
        "superseded_by": suggestion.superseded_by,
    }


def _to_suggestion(data: dict[str, Any]) -> CutSuggestion:
    superseded_by = data.get("superseded_by")
    return CutSuggestion(
        id=str(data["id"]),
        recording_id=str(data["recording_id"]),
        span=Interval(int(data["start_ms"]), int(data["end_ms"])),
        kind=CutKind(data["kind"]),
        reason=str(data["reason"]),
        superseded_by=None if superseded_by is None else str(superseded_by),
    )
