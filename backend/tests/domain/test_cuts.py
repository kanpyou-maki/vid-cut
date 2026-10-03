from vidcut.domain.cuts import effective_cuts
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, EditState, ManualCut


def suggestion(sid: str, start: int, end: int, recording_id: str = "r1") -> CutSuggestion:
    return CutSuggestion(
        id=sid,
        recording_id=recording_id,
        span=Interval(start, end),
        kind=CutKind.SILENCE,
        reason="",
    )


EMPTY = EditState(lecture_id="l1", version=0)


def test_applies_all_suggestions_by_default() -> None:
    suggestions = [suggestion("a", 0, 100), suggestion("b", 500, 800)]
    assert effective_cuts("r1", suggestions, EMPTY) == (Interval(0, 100), Interval(500, 800))


def test_skips_restored_suggestions() -> None:
    suggestions = [suggestion("a", 0, 100), suggestion("b", 500, 800)]
    assert effective_cuts("r1", suggestions, EMPTY.restore("a")) == (Interval(500, 800),)


def test_adds_manual_cuts_and_merges_overlaps() -> None:
    state = EMPTY.add_manual_cut(ManualCut(id="m", recording_id="r1", span=Interval(50, 300)))
    assert effective_cuts("r1", [suggestion("a", 0, 100)], state) == (Interval(0, 300),)


def test_ignores_other_recordings() -> None:
    state = EMPTY.add_manual_cut(ManualCut(id="m", recording_id="r2", span=Interval(0, 10)))
    suggestions = [suggestion("a", 0, 100, recording_id="r2")]
    assert effective_cuts("r1", suggestions, state) == ()
