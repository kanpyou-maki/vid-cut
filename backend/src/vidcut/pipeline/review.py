"""要確認の印（US-04）: 確信度の低いチャンクと、文字が割り当たらない発話。"""

import bisect
from collections.abc import Sequence

from vidcut.domain.intervals import Interval, merge
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
    covered = merge(t.span for t in tokens)
    unrecognized = [
        ReviewMark(recording_id, span, ReviewMarkKind.UNRECOGNIZED_SPEECH)
        for span in speech
        if span.duration_ms >= min_unrecognized_ms and not _overlaps_any(span, covered)
    ]
    return tuple(sorted([*low_confidence, *unrecognized], key=lambda m: m.span))


def _overlaps_any(span: Interval, covered: Sequence[Interval]) -> bool:
    """covered は開始順で重なりのない区間の列。終わりが span の開始より後の最初の区間を見る。"""
    index = bisect.bisect_right(covered, span.start_ms, key=lambda c: c.end_ms)
    return index < len(covered) and covered[index].overlaps(span)
