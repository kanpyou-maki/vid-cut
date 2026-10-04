import json
from pathlib import Path
from typing import Any

import pytest

from vidcut.domain.intervals import Interval
from vidcut.domain.models import Token
from vidcut.domain.timeline import (
    FrameRange,
    build_output_timeline,
    keep_ranges,
    output_duration_ms,
    sentence_pauses,
    to_frames,
    to_output_ms,
)

DURATION = 5000

SHARED_CASES_PATH = Path(__file__).parent / "keep_ranges_cases.json"
"""frontend のプレビューも同じ計算を持つ（frontend/src/editor/keepRanges.ts）。

両側のテストがこのファイルを読んで、同じ入力から同じ結果になることを確かめる。
計算を変えたら、ここに例を足して、両側のテストを通すこと。
"""


def _spans(pairs: list[list[int]]) -> list[Interval]:
    return [Interval(start, end) for start, end in pairs]


@pytest.mark.parametrize(
    "case", json.loads(SHARED_CASES_PATH.read_text()), ids=lambda case: str(case["name"])
)
def test_keep_ranges_matches_the_cases_shared_with_the_frontend(case: dict[str, Any]) -> None:
    kept = keep_ranges(
        case["duration_ms"],
        cuts=_spans(case["cuts"]),
        silences=_spans(case["silences"]),
        pad_before_ms=case["pad_before_ms"],
        pad_after_ms=case["pad_after_ms"],
        # 文の終わりの例だけが持つ。持たない例は、文末の扱いがないときと同じ結果になる
        sentence_pauses=_spans(case.get("sentence_pauses", [])),
        pad_after_sentence_ms=case.get("pad_after_sentence_ms"),
    )
    assert kept == tuple(_spans(case["expected"]))


SENTENCE_PAUSES_CASES_PATH = Path(__file__).parent / "sentence_pauses_cases.json"
"""文の終わりの間の例。frontend（keepRanges.ts の sentencePauses）のテストも同じファイルを読む。"""


def _token(index: int, start_ms: int, end_ms: int, text: str) -> Token:
    return Token(
        id=f"t{index}",
        recording_id="r1",
        chunk_id="c1",
        text=text,
        span=Interval(start_ms, end_ms),
        asr_confidence=0.9,
        align_score=0.9,
    )


@pytest.mark.parametrize(
    "case",
    json.loads(SENTENCE_PAUSES_CASES_PATH.read_text()),
    ids=lambda case: str(case["name"]),
)
def test_sentence_pauses_matches_the_cases_shared_with_the_frontend(case: dict[str, Any]) -> None:
    tokens = [_token(index, *token) for index, token in enumerate(case["tokens"])]

    pauses = sentence_pauses(tokens, _spans(case["silences"]))

    assert pauses == tuple(_spans(case["expected"]))


class TestKeepRanges:
    def test_keeps_everything_without_cuts(self) -> None:
        assert keep_ranges(DURATION, cuts=[], silences=[]) == (Interval(0, DURATION),)

    def test_pads_into_silence_around_a_silence_cut(self) -> None:
        silence = Interval(1000, 2000)
        assert keep_ranges(DURATION, cuts=[silence], silences=[silence]) == (
            Interval(0, 1250),
            Interval(1850, DURATION),
        )

    def test_short_silence_is_kept_when_paddings_meet(self) -> None:
        silence = Interval(1000, 1300)
        assert keep_ranges(DURATION, cuts=[silence], silences=[silence]) == (Interval(0, DURATION),)

    def test_does_not_pad_a_cut_inside_speech(self) -> None:
        assert keep_ranges(DURATION, cuts=[Interval(1000, 1500)], silences=[]) == (
            Interval(0, 1000),
            Interval(1500, DURATION),
        )

    def test_pads_only_into_the_silence_next_to_kept_speech(self) -> None:
        silences = [Interval(1500, 2000), Interval(3000, 3600)]
        cuts = [*silences, Interval(2000, 3000)]  # 言い直しのチャンクと前後の無音
        assert keep_ranges(DURATION, cuts=cuts, silences=silences) == (
            Interval(0, 1750),
            Interval(3450, DURATION),
        )

    def test_padding_stops_at_silence_boundary(self) -> None:
        silences = [Interval(1000, 1100)]
        cuts = [Interval(1000, 1100), Interval(1100, 2000)]
        assert keep_ranges(DURATION, cuts=cuts, silences=silences) == (
            Interval(0, 1100),
            Interval(2000, DURATION),
        )

    def test_pads_across_touching_silences(self) -> None:
        silences = [Interval(0, 1000), Interval(1000, 2000)]
        cuts = [Interval(0, 1050), Interval(2000, 3000)]
        assert keep_ranges(DURATION, cuts=cuts, silences=silences) == (
            Interval(900, 2000),
            Interval(3000, DURATION),
        )

    def test_manual_cut_starting_inside_silence_keeps_padding_within_silence(self) -> None:
        silences = [Interval(1000, 2000)]
        assert keep_ranges(DURATION, cuts=[Interval(1500, 3000)], silences=silences) == (
            Interval(0, 1750),
            Interval(3000, DURATION),
        )

    def test_returns_empty_when_everything_is_cut(self) -> None:
        assert keep_ranges(DURATION, cuts=[Interval(0, DURATION)], silences=[]) == ()

    def test_custom_padding(self) -> None:
        silence = Interval(1000, 2000)
        result = keep_ranges(
            DURATION, cuts=[silence], silences=[silence], pad_before_ms=0, pad_after_ms=0
        )
        assert result == (Interval(0, 1000), Interval(2000, DURATION))

    def test_sentence_padding_defaults_to_the_usual_padding(self) -> None:
        # 文末用の値を渡さなければ、文の終わりでも通常の余白
        kept = keep_ranges(
            5_000,
            cuts=[Interval(1_000, 2_000)],
            silences=[Interval(1_000, 2_000)],
            sentence_pauses=[Interval(900, 2_000)],
        )
        assert kept == (Interval(0, 1_250), Interval(1_850, 5_000))

    def test_rejects_negative_sentence_padding(self) -> None:
        with pytest.raises(ValueError, match="余白"):
            keep_ranges(5_000, cuts=[], silences=[], pad_after_sentence_ms=-1)

    def test_rejects_negative_padding(self) -> None:
        with pytest.raises(ValueError):
            keep_ranges(DURATION, cuts=[], silences=[], pad_before_ms=-1)

    def test_rejects_non_positive_duration(self) -> None:
        with pytest.raises(ValueError):
            keep_ranges(0, cuts=[], silences=[])


class TestToFrames:
    def test_floors_start_and_ceils_end_at_60fps(self) -> None:
        assert to_frames([Interval(1001, 1249)], fps=60) == (FrameRange(60, 75),)

    def test_exact_boundaries_stay(self) -> None:
        assert to_frames([Interval(1000, 1250)], fps=60) == (FrameRange(60, 75),)

    def test_merges_ranges_that_overlap_after_rounding(self) -> None:
        assert to_frames([Interval(0, 1001), Interval(1010, 2000)], fps=60) == (FrameRange(0, 120),)

    def test_rejects_non_positive_fps(self) -> None:
        with pytest.raises(ValueError):
            to_frames([Interval(0, 10)], fps=0)

    def test_frame_range_rejects_empty_range(self) -> None:
        with pytest.raises(ValueError):
            FrameRange(10, 10)

    def test_frame_range_duration(self) -> None:
        assert FrameRange(60, 75).duration_frames == 15


class TestOutputTimeline:
    timeline = build_output_timeline(
        [
            ("r1", (Interval(0, 1000), Interval(2000, 3000))),
            ("r2", (Interval(500, 1500),)),
        ]
    )

    def test_maps_source_time_to_output_time(self) -> None:
        assert to_output_ms(self.timeline, "r1", 0) == 0
        assert to_output_ms(self.timeline, "r1", 2500) == 1500
        assert to_output_ms(self.timeline, "r2", 600) == 2100

    def test_returns_none_for_cut_or_unknown_time(self) -> None:
        assert to_output_ms(self.timeline, "r1", 1500) is None
        assert to_output_ms(self.timeline, "r3", 0) is None

    def test_output_duration_is_sum_of_kept_ranges(self) -> None:
        assert output_duration_ms(self.timeline) == 3000

    def test_empty_timeline(self) -> None:
        assert output_duration_ms(build_output_timeline([])) == 0


@pytest.mark.parametrize("bad", [1.5, True])
def test_frame_range_rejects_non_int_values(bad: object) -> None:
    with pytest.raises(TypeError):
        FrameRange(bad, 100)  # type: ignore[arg-type]
