import pytest

from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, EditState, ManualCut
from vidcut.domain.overrides import carry_over_analysis_restorations, carry_over_restorations


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


def test_rejects_negative_tolerance() -> None:
    with pytest.raises(ValueError):
        carry_over_restorations(BASE, [], [], tolerance_ms=-1)


class TestCarryOverAnalysisRestorations:
    """解析し直したとき、戻した無音・フィラーを、区間で新しい候補へ引き継ぐ（id では見ない）。"""

    def test_widened_filler_keeps_its_restoration_under_the_new_id(self) -> None:
        old = cut("r1-c0003-filler-1", 5_600, 5_800, CutKind.FILLER)
        new = cut("r1-c0003-filler-0", 5_400, 5_950, CutKind.FILLER)
        state = carry_over_analysis_restorations(BASE.restore(old.id), [old], [new])
        assert state.restored_suggestion_ids == frozenset({new.id})

    def test_same_id_that_now_means_another_filler_is_not_trusted(self) -> None:
        # 前の filler-0 はなくなり、同じ id が別のフィラーを指すようになった
        old = cut("r1-c0003-filler-0", 1_000, 1_200, CutKind.FILLER)
        new = cut("r1-c0003-filler-0", 7_000, 7_500, CutKind.FILLER)
        state = carry_over_analysis_restorations(BASE.restore(old.id), [old], [new])
        assert state.restored_suggestion_ids == frozenset()

    def test_fillers_merged_into_one_restore_the_merged_one(self) -> None:
        first = cut("r1-c0003-filler-0", 1_000, 1_200, CutKind.FILLER)
        second = cut("r1-c0003-filler-1", 1_300, 1_600, CutKind.FILLER)
        merged = cut("r1-c0003-filler-0", 950, 1_700, CutKind.FILLER)
        state = carry_over_analysis_restorations(BASE.restore(second.id), [first, second], [merged])
        assert state.restored_suggestion_ids == frozenset({merged.id})

    def test_filler_split_into_two_restores_both(self) -> None:
        old = cut("r1-c0003-filler-0", 1_000, 2_000, CutKind.FILLER)
        parts = [
            cut("r1-c0003-filler-0", 1_000, 1_400, CutKind.FILLER),
            cut("r1-c0003-filler-1", 1_600, 2_000, CutKind.FILLER),
        ]
        state = carry_over_analysis_restorations(BASE.restore(old.id), [old], parts)
        assert state.restored_suggestion_ids == frozenset({parts[0].id, parts[1].id})

    def test_does_not_map_across_kinds_or_recordings(self) -> None:
        old = cut("r1-c0003-filler-0", 1_000, 1_200, CutKind.FILLER)
        others = [
            cut("r1-silence-0001", 900, 1_300, CutKind.SILENCE),
            cut("r2-c0000-filler-0", 1_000, 1_200, CutKind.FILLER, recording_id="r2"),
        ]
        state = carry_over_analysis_restorations(BASE.restore(old.id), [old], others)
        assert state.restored_suggestion_ids == frozenset()

    def test_touching_spans_do_not_count_as_overlap(self) -> None:
        old = cut("r1-c0003-filler-0", 1_000, 1_200, CutKind.FILLER)
        new = cut("r1-c0003-filler-0", 1_200, 1_500, CutKind.FILLER)
        state = carry_over_analysis_restorations(BASE.restore(old.id), [old], [new])
        assert state.restored_suggestion_ids == frozenset()

    def test_restorations_of_other_candidates_stay(self) -> None:
        # 言い直しの候補と、ほかの録画ファイルの候補は、解析し直しでは触れない
        old = cut("r1-silence-0000", 0, 500, CutKind.SILENCE)
        state = BASE.restore("r1-c0001-judged").restore("r2-silence-0000").restore(old.id)
        carried = carry_over_analysis_restorations(state, [old], [old])
        assert carried.restored_suggestion_ids == state.restored_suggestion_ids

    def test_unchanged_state_is_returned_as_it_is(self) -> None:
        silence = cut("r1-silence-0000", 0, 500, CutKind.SILENCE)
        state = BASE.restore(silence.id)
        assert carry_over_analysis_restorations(state, [silence], [silence]) is state

    def test_preserves_version_and_manual_cuts(self) -> None:
        old = cut("r1-c0003-filler-1", 5_600, 5_800, CutKind.FILLER)
        new = cut("r1-c0003-filler-0", 5_400, 5_950, CutKind.FILLER)
        manual = ManualCut("m1", "r1", Interval(0, 100))
        state = EditState("l1", 7, frozenset({old.id}), (manual,))
        carried = carry_over_analysis_restorations(state, [old], [new])
        assert (carried.version, carried.manual_cuts) == (7, (manual,))
