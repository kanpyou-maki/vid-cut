import math

import pytest

from vidcut.domain.intervals import Interval
from vidcut.domain.models import SpeechChunk
from vidcut.pipeline.ports import AlignedChar, ChunkTranscript
from vidcut.pipeline.transcript import build_tokens

CHUNK = SpeechChunk(id="r1-c0001", recording_id="r1", span=Interval(1_000, 2_000))


def char(text: str, start: int | None, end: int | None, score: float | None = 0.9) -> AlignedChar:
    return AlignedChar(text=text, start_ms=start, end_ms=end, score=score)


class TestBuildTokens:
    def test_one_token_per_character_with_its_timing(self) -> None:
        chars = [char("こ", 1_000, 1_100), char("れ", 1_100, 1_250, 0.5)]
        tokens = build_tokens(CHUNK, ChunkTranscript("これ", -0.2), chars)
        assert [(t.text, t.span) for t in tokens] == [
            ("こ", Interval(1_000, 1_100)),
            ("れ", Interval(1_100, 1_250)),
        ]
        assert [t.align_score for t in tokens] == [0.9, 0.5]
        assert all(t.chunk_id == CHUNK.id and t.recording_id == "r1" for t in tokens)

    def test_ids_are_unique_and_ordered_within_chunk(self) -> None:
        chars = [char("あ", 1_000, 1_100), char("い", 1_100, 1_200)]
        tokens = build_tokens(CHUNK, ChunkTranscript("あい", 0.0), chars)
        assert [t.id for t in tokens] == ["r1-c0001-t000", "r1-c0001-t001"]

    def test_asr_confidence_comes_from_chunk_log_probability(self) -> None:
        tokens = build_tokens(CHUNK, ChunkTranscript("あ", -0.5), [char("あ", 1_000, 1_100)])
        assert tokens[0].asr_confidence == pytest.approx(math.exp(-0.5))

    def test_positive_log_probability_is_capped_at_one(self) -> None:
        tokens = build_tokens(CHUNK, ChunkTranscript("あ", 0.01), [char("あ", 1_000, 1_100)])
        assert tokens[0].asr_confidence == 1.0

    def test_whitespace_is_dropped(self) -> None:
        chars = [char("あ", 1_000, 1_100), char(" ", None, None), char("い", 1_300, 1_400)]
        tokens = build_tokens(CHUNK, ChunkTranscript("あ い", 0.0), chars)
        assert [t.text for t in tokens] == ["あ", "い"]

    def test_untimed_characters_share_the_gap_between_neighbors(self) -> None:
        chars = [
            char("あ", 1_000, 1_100),
            char("、", None, None, None),
            char("。", None, None, None),
            char("い", 1_300, 1_400),
        ]
        tokens = build_tokens(CHUNK, ChunkTranscript("あ、。い", 0.0), chars)
        assert [t.span for t in tokens[1:3]] == [Interval(1_100, 1_200), Interval(1_200, 1_300)]
        assert tokens[1].align_score == 0.0

    def test_untimed_characters_at_edges_use_chunk_bounds(self) -> None:
        chars = [char("「", None, None), char("あ", 1_200, 1_300), char("」", None, None)]
        tokens = build_tokens(CHUNK, ChunkTranscript("「あ」", 0.0), chars)
        assert tokens[0].span == Interval(1_000, 1_200)
        assert tokens[2].span == Interval(1_300, 2_000)

    def test_zero_length_and_out_of_chunk_times_are_repaired(self) -> None:
        chars = [char("あ", 900, 900), char("い", 1_950, 2_300)]
        tokens = build_tokens(CHUNK, ChunkTranscript("あい", 0.0), chars)
        assert tokens[0].span == Interval(1_000, 1_001)
        assert tokens[1].span == Interval(1_950, 2_000)

    def test_no_crowding_when_gap_is_too_small(self) -> None:
        chars = [char("あ", 1_000, 1_100), char("、", None, None), char("い", 1_100, 1_200)]
        tokens = build_tokens(CHUNK, ChunkTranscript("あ、い", 0.0), chars)
        assert tokens[1].span.duration_ms >= 1

    def test_empty_transcript_has_no_tokens(self) -> None:
        assert build_tokens(CHUNK, ChunkTranscript("", -1.0), []) == ()
