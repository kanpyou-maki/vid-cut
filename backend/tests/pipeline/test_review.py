from vidcut.domain.intervals import Interval
from vidcut.domain.models import ReviewMark, ReviewMarkKind, SpeechChunk, Token
from vidcut.pipeline.ports import ChunkTranscript
from vidcut.pipeline.review import review_marks


def chunk(index: int, start: int, end: int) -> SpeechChunk:
    return SpeechChunk(id=f"r1-c{index:04d}", recording_id="r1", span=Interval(start, end))


def token(start: int, end: int) -> Token:
    return Token(
        id=f"t{start}",
        recording_id="r1",
        chunk_id="r1-c0000",
        text="あ",
        span=Interval(start, end),
        asr_confidence=0.9,
        align_score=0.9,
    )


def marks(
    chunks: list[SpeechChunk],
    transcripts: list[ChunkTranscript],
    tokens: list[Token],
    speech: list[Interval],
) -> tuple[ReviewMark, ...]:
    return review_marks(
        "r1",
        chunks,
        transcripts,
        tokens,
        speech,
        low_logprob=-0.5,
        min_unrecognized_ms=200,
    )


class TestReviewMarks:
    def test_low_confidence_chunk_is_marked(self) -> None:
        chunks = [chunk(0, 0, 1_000), chunk(1, 2_000, 3_000)]
        transcripts = [ChunkTranscript("a", -0.2), ChunkTranscript("b", -0.8)]
        result = marks(chunks, transcripts, [token(2_000, 2_100)], speech=[])
        assert result == (
            ReviewMark(
                recording_id="r1", span=Interval(2_000, 3_000), kind=ReviewMarkKind.LOW_CONFIDENCE
            ),
        )

    def test_speech_without_any_characters_is_marked(self) -> None:
        # Whisper が書き起こさなかったフィラーなど
        speech = [Interval(0, 500), Interval(1_000, 1_600)]
        result = marks([], [], [token(100, 200)], speech)
        assert result == (
            ReviewMark(
                recording_id="r1",
                span=Interval(1_000, 1_600),
                kind=ReviewMarkKind.UNRECOGNIZED_SPEECH,
            ),
        )

    def test_short_unrecognized_speech_is_ignored(self) -> None:
        assert marks([], [], [], [Interval(0, 150)]) == ()

    def test_marks_are_sorted_by_time(self) -> None:
        chunks = [chunk(0, 1_000, 2_000)]
        result = marks(chunks, [ChunkTranscript("x", -1.0)], [], [Interval(0, 400)])
        assert [m.span.start_ms for m in result] == [0, 1_000]
