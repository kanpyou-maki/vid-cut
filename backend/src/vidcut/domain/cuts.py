"""実際に削除される区間の計算（Design Doc 4 章）。"""

from collections.abc import Iterable

from vidcut.domain.intervals import Interval, merge
from vidcut.domain.models import CutSuggestion, EditState


def effective_cuts(
    recording_id: str, suggestions: Iterable[CutSuggestion], state: EditState
) -> tuple[Interval, ...]:
    """（自動の削除候補 − 戻したもの）∪ 人が追加した削除区間 を、録画ファイルごとに統合して返す。"""
    auto = (
        s.span
        for s in suggestions
        if s.recording_id == recording_id and s.id not in state.restored_suggestion_ids
    )
    manual = (c.span for c in state.manual_cuts if c.recording_id == recording_id)
    return merge([*auto, *manual])
