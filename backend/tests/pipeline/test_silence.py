import pytest

from vidcut.domain.intervals import Interval
from vidcut.pipeline.silence import find_silences, split_chunks


class TestFindSilences:
    def test_quiet_span_without_speech_is_silence(self) -> None:
        assert find_silences([Interval(1_000, 2_000)], speech=[], min_ms=300) == (
            Interval(1_000, 2_000),
        )

    def test_quiet_speech_detected_by_vad_is_not_silence(self) -> None:
        # 小声の発話を削除しないよう、VAD が発話とした部分は無音から除く
        silences = find_silences(
            [Interval(1_000, 2_000)], speech=[Interval(1_400, 1_600)], min_ms=300
        )
        assert silences == (Interval(1_000, 1_400), Interval(1_600, 2_000))

    def test_pieces_shorter_than_minimum_are_dropped(self) -> None:
        silences = find_silences(
            [Interval(1_000, 2_000)], speech=[Interval(1_200, 1_900)], min_ms=300
        )
        assert silences == ()

    def test_loud_non_speech_is_not_silence(self) -> None:
        # 音量で無音でなければ（キーボードの音など）、VAD が発話なしでも無音にしない
        assert find_silences([], speech=[], min_ms=300) == ()

    def test_results_are_sorted_and_merged(self) -> None:
        silences = find_silences(
            [Interval(5_000, 6_000), Interval(1_000, 1_500), Interval(1_500, 2_000)],
            speech=[],
            min_ms=300,
        )
        assert silences == (Interval(1_000, 2_000), Interval(5_000, 6_000))

    def test_rejects_negative_minimum(self) -> None:
        with pytest.raises(ValueError):
            find_silences([], speech=[], min_ms=-1)


class TestSplitChunks:
    def test_chunks_are_the_gaps_between_silences(self) -> None:
        chunks = split_chunks(10_000, [Interval(0, 1_000), Interval(4_000, 5_000)], min_ms=100)
        assert chunks == (Interval(1_000, 4_000), Interval(5_000, 10_000))

    def test_whole_recording_is_one_chunk_without_silence(self) -> None:
        assert split_chunks(3_000, [], min_ms=100) == (Interval(0, 3_000),)

    def test_tiny_fragments_are_dropped(self) -> None:
        chunks = split_chunks(3_000, [Interval(0, 1_000), Interval(1_050, 3_000)], min_ms=100)
        assert chunks == ()

    def test_rejects_non_positive_duration(self) -> None:
        with pytest.raises(ValueError):
            split_chunks(0, [], min_ms=100)
