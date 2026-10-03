"""判定をやり直したときの「戻した削除候補」の引き継ぎ（Design Doc 4 章）。"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from vidcut.domain.models import CutSuggestion, EditState

DEFAULT_TOLERANCE_MS = 200


@dataclass(frozen=True)
class CarryOverResult:
    state: EditState
    dropped_suggestion_ids: tuple[str, ...]


def carry_over_restorations(
    state: EditState,
    old_suggestions: Iterable[CutSuggestion],
    new_suggestions: Iterable[CutSuggestion],
    tolerance_ms: int = DEFAULT_TOLERANCE_MS,
) -> CarryOverResult:
    """戻した削除候補を、作り直した削除候補の集合へ引き継ぐ。

    同じ id が残っていればそのまま。言い直し系の候補は、同じ録画ファイルで開始・終了の差が
    tolerance_ms 以内の言い直し系の新しい候補へ付け替える。引き継げなかったものは破棄して返す。
    """
    if tolerance_ms < 0:
        raise ValueError(f"tolerance_ms は 0 以上である必要があります: {tolerance_ms}")

    old_by_id = {s.id: s for s in old_suggestions}
    new = tuple(new_suggestions)
    new_ids = {s.id for s in new}

    kept: set[str] = set()
    dropped: list[str] = []
    for sid in sorted(state.restored_suggestion_ids):
        target = sid if sid in new_ids else _find_match(old_by_id.get(sid), new, tolerance_ms)
        if target is None:
            dropped.append(sid)
        else:
            kept.add(target)

    return CarryOverResult(
        state=replace(state, restored_suggestion_ids=frozenset(kept)),
        dropped_suggestion_ids=tuple(dropped),
    )


def _find_match(
    old: CutSuggestion | None, candidates: Sequence[CutSuggestion], tolerance_ms: int
) -> str | None:
    if old is None or not old.kind.is_rejudged:
        return None
    for candidate in candidates:
        if (
            candidate.kind.is_rejudged
            and candidate.recording_id == old.recording_id
            and abs(candidate.span.start_ms - old.span.start_ms) <= tolerance_ms
            and abs(candidate.span.end_ms - old.span.end_ms) <= tolerance_ms
        ):
            return candidate.id
    return None
