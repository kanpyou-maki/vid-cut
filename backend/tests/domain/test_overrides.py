from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, EditState, ManualCut
from vidcut.domain.overrides import carry_over_restorations


def cut(
    sid: str, start: int, end: int, kind: CutKind = CutKind.RETAKE, recording_id: str = "r1"
) -> CutSuggestion:
    reason = "" if kind in {CutKind.SILENCE, CutKind.FILLER} else "言い直し"
    return CutSuggestion(sid, recording_id, Interval(start, end), kind, reason)


BASE = EditState(lecture_id="l1", version=3)


def test_keeps_restored_suggestion_that_still_exists() -> None:
    silence = cut("s1", 0, 500, CutKind.SILENCE)
    result = carry_over_restorations(BASE.restore("s1"), [silence], [silence])
    assert result.state.restored_suggestion_ids == frozenset({"s1"})
    assert result.dropped_suggestion_ids == ()


def test_maps_restored_retake_to_new_suggestion_with_nearly_same_span() -> None:
    old = cut("old", 1000, 2000)
    new = cut("new", 1100, 1950, CutKind.MISSPEAK)
    result = carry_over_restorations(BASE.restore("old"), [old], [new])
    assert result.state.restored_suggestion_ids == frozenset({"new"})
    assert result.dropped_suggestion_ids == ()


def test_drops_restored_retake_without_a_close_match() -> None:
    old = cut("old", 1000, 2000)
    new = cut("new", 1500, 2600)
    result = carry_over_restorations(BASE.restore("old"), [old], [new])
    assert result.state.restored_suggestion_ids == frozenset()
    assert result.dropped_suggestion_ids == ("old",)


def test_does_not_match_across_recordings() -> None:
    old = cut("old", 1000, 2000)
    new = cut("new", 1000, 2000, recording_id="r2")
    result = carry_over_restorations(BASE.restore("old"), [old], [new])
    assert result.dropped_suggestion_ids == ("old",)


def test_does_not_map_retake_to_silence_suggestion() -> None:
    old = cut("old", 1000, 2000)
    new = cut("new", 1000, 2000, CutKind.SILENCE)
    result = carry_over_restorations(BASE.restore("old"), [old], [new])
    assert result.dropped_suggestion_ids == ("old",)


def test_drops_unknown_restored_ids() -> None:
    result = carry_over_restorations(BASE.restore("ghost"), [], [])
    assert result.dropped_suggestion_ids == ("ghost",)


def test_preserves_version_and_manual_cuts() -> None:
    manual = ManualCut("m1", "r1", Interval(0, 10))
    state = BASE.add_manual_cut(manual)
    result = carry_over_restorations(state, [], [])
    assert result.state.version == 3
    assert result.state.manual_cuts == (manual,)


def test_custom_tolerance() -> None:
    old = cut("old", 1000, 2000)
    new = cut("new", 1300, 2000)
    strict = carry_over_restorations(BASE.restore("old"), [old], [new])
    loose = carry_over_restorations(BASE.restore("old"), [old], [new], tolerance_ms=300)
    assert strict.dropped_suggestion_ids == ("old",)
    assert loose.state.restored_suggestion_ids == frozenset({"new"})


def test_tolerance_boundary_is_inclusive() -> None:
    old = cut("old", 1000, 2000)
    at_limit = cut("at", 1200, 1800)
    beyond = cut("beyond", 1201, 2000)
    assert carry_over_restorations(BASE.restore("old"), [old], [at_limit]).state == BASE.restore(
        "at"
    )
    assert carry_over_restorations(BASE.restore("old"), [old], [beyond]).dropped_suggestion_ids == (
        "old",
    )
