"""判定や解析をやり直したときの「戻した削除候補」の引き継ぎ（Design Doc 4 章）。"""

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


def carry_over_analysis_restorations(
    state: EditState,
    old_suggestions: Iterable[CutSuggestion],
    new_suggestions: Iterable[CutSuggestion],
) -> EditState:
    """解析し直したとき、戻した無音・フィラーの候補を、新しい候補へ引き継ぐ。

    無音とフィラーの id は「何番目か」で決まるので、検出のしかたが変わると、同じ id が別の候補を
    指すことがある。そのため id ではなく区間で対応づける: 戻していた候補と重なる、同じ録画ファイルの
    同じ種類の新しい候補を、すべて戻す（迷ったら残す）。重なる候補がなければ、その区間はもう
    削除されないので、戻した記録は捨てる。

    old_suggestions は、解析し直す前の、その録画ファイルの解析の候補。そこにない id
    （言い直しの候補、ほかの録画ファイルの候補）には触れない。
    何も変わらなければ、渡された state をそのまま返す。
    """
    old_by_id = {s.id: s for s in old_suggestions}
    new = tuple(new_suggestions)
    carried: set[str] = set()
    for sid in state.restored_suggestion_ids:
        old = old_by_id.get(sid)
        if old is None:
            carried.add(sid)
        else:
            carried.update(candidate.id for candidate in new if _replaces(candidate, old))
    if carried == state.restored_suggestion_ids:
        return state
    return replace(state, restored_suggestion_ids=frozenset(carried))


def _replaces(candidate: CutSuggestion, old: CutSuggestion) -> bool:
    return (
        candidate.kind is old.kind
        and candidate.recording_id == old.recording_id
        and candidate.span.overlaps(old.span)
    )
