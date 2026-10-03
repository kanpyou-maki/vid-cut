import pytest

from vidcut.domain.intervals import Interval
from vidcut.pipeline.silence import extend_to_end, find_silences, split_chunks


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

    def test_vad_speech_crossing_the_edges_does_not_shrink_silence(self) -> None:
        # VAD の発話区間は前後に余韻を含み、短い無音もまたぐ。音量の無音の端は動かさない
        silences = find_silences(
            [Interval(1_000, 2_000), Interval(3_000, 3_400)],
            speech=[Interval(0, 1_250), Interval(2_900, 4_000)],
            min_ms=300,
        )
        assert silences == (Interval(1_000, 2_000), Interval(3_000, 3_400))

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


class TestExtendToEnd:
    """解析用の音声は、録画ファイルの長さ（probe の値）より数十 ms 早く終わることがある。"""

    def test_silence_reaching_the_end_of_the_audio_extends_to_the_end_of_the_recording(
        self,
    ) -> None:
        # 実素材: 音声は 368,946ms まで、録画ファイルの長さは 368,977ms
        silences = [Interval(0, 8_248), Interval(364_369, 368_946)]
        assert extend_to_end(silences, 368_977) == (
            Interval(0, 8_248),
            Interval(364_369, 368_977),
        )

    def test_silence_that_ends_well_before_the_end_is_left_alone(self) -> None:
        # 最後まで話している。終わりの 500ms は発話
        silences = [Interval(1_000, 9_500)]
        assert extend_to_end(silences, 10_000) == (Interval(1_000, 9_500),)

    def test_silence_already_reaching_the_end_is_unchanged(self) -> None:
        assert extend_to_end([Interval(9_000, 10_000)], 10_000) == (Interval(9_000, 10_000),)

    def test_only_the_last_silence_is_extended(self) -> None:
        silences = [Interval(9_000, 9_930), Interval(9_950, 9_980)]
        assert extend_to_end(silences, 10_000) == (
            Interval(9_000, 9_930),
            Interval(9_950, 10_000),
        )

    def test_no_silences(self) -> None:
        assert extend_to_end([], 10_000) == ()

    def test_tolerance_is_configurable(self) -> None:
        assert extend_to_end([Interval(0, 9_500)], 10_000, tolerance_ms=500) == (
            Interval(0, 10_000),
        )
        assert extend_to_end([Interval(0, 9_499)], 10_000, tolerance_ms=500) == (
            Interval(0, 9_499),
        )

    @pytest.mark.parametrize(("duration_ms", "tolerance_ms"), [(0, 100), (10_000, -1)])
    def test_rejects_invalid_arguments(self, duration_ms: int, tolerance_ms: int) -> None:
        with pytest.raises(ValueError):
            extend_to_end([], duration_ms, tolerance_ms=tolerance_ms)
