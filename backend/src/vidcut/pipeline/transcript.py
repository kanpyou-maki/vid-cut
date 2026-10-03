"""位置合わせの結果 → 文字単位の Token（Design Doc 3-2 段 7、ADR-003）。"""

import math
from collections.abc import Sequence

from vidcut.domain.intervals import Interval
from vidcut.domain.models import SpeechChunk, Token
from vidcut.pipeline.ports import AlignedChar, ChunkTranscript


def build_tokens(
    chunk: SpeechChunk, transcript: ChunkTranscript, chars: Sequence[AlignedChar]
) -> tuple[Token, ...]:
    """空白を除いた 1 文字ずつを Token にする。

    時刻が付かなかった文字（句読点など）は、前後の時刻の付いた文字の間を等分して割り当てる。
    時刻はチャンクの範囲に収め、長さ 0 にならないよう補う。
    """
    visible = [c for c in chars if c.text.strip()]
    spans = _fill_spans(chunk.span, visible)
    confidence = min(1.0, math.exp(transcript.avg_logprob))
    return tuple(
        Token(
            id=f"{chunk.id}-t{index:03d}",
            recording_id=chunk.recording_id,
            chunk_id=chunk.id,
            text=c.text,
            span=span,
            asr_confidence=confidence,
            align_score=c.score if c.score is not None else 0.0,
        )
        for index, (c, span) in enumerate(zip(visible, spans, strict=True))
    )


def _fill_spans(bounds: Interval, chars: Sequence[AlignedChar]) -> list[Interval]:
    known = [_known_span(bounds, c) for c in chars]
    spans: list[Interval] = []
    index = 0
    while index < len(chars):
        span = known[index]
        if span is not None:
            spans.append(span)
            index += 1
            continue
        run_end = index
        while run_end < len(chars) and known[run_end] is None:
            run_end += 1
        left = spans[-1].end_ms if spans else bounds.start_ms
        next_known = known[run_end] if run_end < len(chars) else None
        right = next_known.start_ms if next_known else bounds.end_ms
        spans.extend(_divide(bounds, left, right, run_end - index))
        index = run_end
    return spans


def _known_span(bounds: Interval, c: AlignedChar) -> Interval | None:
    if c.start_ms is None or c.end_ms is None:
        return None
    return _clamped(bounds, c.start_ms, c.end_ms)


def _divide(bounds: Interval, left: int, right: int, count: int) -> list[Interval]:
    width = max(right - left, 0) / count
    return [
        _clamped(bounds, left + round(width * i), left + round(width * (i + 1)))
        for i in range(count)
    ]


def _clamped(bounds: Interval, start_ms: int, end_ms: int) -> Interval:
    start = min(max(start_ms, bounds.start_ms), bounds.end_ms - 1)
    end = min(max(end_ms, start + 1), bounds.end_ms)
    return Interval(start, end)
