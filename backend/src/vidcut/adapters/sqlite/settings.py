"""SettingsRepository の SQLite 実装。設定は、名前ごとに 1 行の JSON で持つ。"""

import json
import logging
import sqlite3

from vidcut.adapters.sqlite.database import NOW, transaction
from vidcut.domain.timeline import KeepPadding

_KEEP_PADDING = "keep_padding"
_PADDING_FIELDS = {"before_ms", "after_ms", "after_sentence_ms"}

_logger = logging.getLogger(__name__)


class SqliteSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def keep_padding(self) -> KeepPadding | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (_KEEP_PADDING,)
        ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row["value"])
            # 3 つの値がそろっているものだけを使う（欠けた値を既定値で補わない）
            if not isinstance(data, dict) or set(data) != _PADDING_FIELDS:
                raise ValueError("余白の項目がそろっていません")
            return KeepPadding(**data)
        except (ValueError, RecursionError):
            # 壊れた値で書き出しを止めない。既定値に戻る
            # （RecursionError は、極端に深い入れ子の JSON。データベースを直接書き換えたとき）
            _logger.warning("保存された余白の設定を読めないため、既定値を使います")
            return None

    def save_keep_padding(self, padding: KeepPadding) -> None:
        value = json.dumps(
            {
                "before_ms": padding.before_ms,
                "after_ms": padding.after_ms,
                "after_sentence_ms": padding.after_sentence_ms,
            }
        )
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                f" ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = {NOW}",
                (_KEEP_PADDING, value),
            )

    def clear_keep_padding(self) -> None:
        with transaction(self._conn):
            self._conn.execute("DELETE FROM settings WHERE key = ?", (_KEEP_PADDING,))
