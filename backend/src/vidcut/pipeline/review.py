"""要確認の印（US-04）: 確信度の低いチャンクと、文字が割り当たらない発話。"""

from collections.abc import Sequence

from vidcut.domain.intervals import Interval
from vidcut.domain.models import ReviewMark, ReviewMarkKind, SpeechChunk, Token
from vidcut.pipeline.ports import ChunkTranscript


def review_marks(
    recording_id: str,
    chunks: Sequence[SpeechChunk],
    transcripts: Sequence[ChunkTranscript],
    tokens: Sequence[Token],
    speech: Sequence[Interval],
    *,
    low_logprob: float,
    min_unrecognized_ms: int,
) -> tuple[ReviewMark, ...]:
    """chunks と transcripts は同じ順。speech は VAD が発話とした区間。"""
    low_confidence = [
        ReviewMark(recording_id, chunk.span, ReviewMarkKind.LOW_CONFIDENCE)
        for chunk, transcript in zip(chunks, transcripts, strict=True)
        if transcript.avg_logprob < low_logprob
    ]
    # Whisper はフィラーなどを書き起こさないことがある。削除はせず、人に聞いてもらう
    unrecognized = [
        ReviewMark(recording_id, span, ReviewMarkKind.UNRECOGNIZED_SPEECH)
        for span in speech
        if span.duration_ms >= min_unrecognized_ms
        and not any(t.span.overlaps(span) for t in tokens)
    ]
    return tuple(sorted([*low_confidence, *unrecognized], key=lambda m: m.span))
