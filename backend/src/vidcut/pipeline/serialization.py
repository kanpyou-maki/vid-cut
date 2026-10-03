"""解析結果と JSON（ワークスペースに保存する形）の相互変換。読み込みでは形を検証する。"""

from collections.abc import Callable
from typing import Any

from vidcut.domain.intervals import Interval
from vidcut.domain.models import (
    CutKind,
    CutSuggestion,
    ReviewMark,
    ReviewMarkKind,
    Silence,
    SpeechChunk,
    Token,
)
from vidcut.pipeline.ports import ChunkTranscript, Peaks

Json = Any


def span_to(span: Interval) -> list[int]:
    return [span.start_ms, span.end_ms]


def span_from(data: Json) -> Interval:
    start, end = data
    return Interval(int(start), int(end))


def chunk_to(chunk: SpeechChunk) -> Json:
    return {"id": chunk.id, "span": span_to(chunk.span)}


def chunk_from(data: Json, recording_id: str) -> SpeechChunk:
    return SpeechChunk(id=str(data["id"]), recording_id=recording_id, span=span_from(data["span"]))


def token_to(token: Token) -> Json:
    return {
        "id": token.id,
        "chunk_id": token.chunk_id,
        "text": token.text,
        "span": span_to(token.span),
        "asr_confidence": token.asr_confidence,
        "align_score": token.align_score,
    }


def token_from(data: Json, recording_id: str) -> Token:
    return Token(
        id=str(data["id"]),
        recording_id=recording_id,
        chunk_id=str(data["chunk_id"]),
        text=str(data["text"]),
        span=span_from(data["span"]),
        asr_confidence=float(data["asr_confidence"]),
        align_score=float(data["align_score"]),
    )


def suggestion_to(suggestion: CutSuggestion) -> Json:
    return {
        "id": suggestion.id,
        "span": span_to(suggestion.span),
        "kind": suggestion.kind.value,
        "reason": suggestion.reason,
        "superseded_by": suggestion.superseded_by,
    }


def suggestion_from(data: Json, recording_id: str) -> CutSuggestion:
    superseded_by = data.get("superseded_by")
    return CutSuggestion(
        id=str(data["id"]),
        recording_id=recording_id,
        span=span_from(data["span"]),
        kind=CutKind(data["kind"]),
        reason=str(data["reason"]),
        superseded_by=None if superseded_by is None else str(superseded_by),
    )


def mark_to(mark: ReviewMark) -> Json:
    return {"span": span_to(mark.span), "kind": mark.kind.value}


def mark_from(data: Json, recording_id: str) -> ReviewMark:
    return ReviewMark(
        recording_id=recording_id, span=span_from(data["span"]), kind=ReviewMarkKind(data["kind"])
    )


def silence_from(data: Json, recording_id: str) -> Silence:
    return Silence(recording_id=recording_id, span=span_from(data))


def transcript_to(transcript: ChunkTranscript) -> Json:
    return {"text": transcript.text, "avg_logprob": transcript.avg_logprob}


def transcript_from(data: Json) -> ChunkTranscript:
    return ChunkTranscript(text=str(data["text"]), avg_logprob=float(data["avg_logprob"]))


def peaks_to(peaks: Peaks) -> Json:
    return {"per_second": peaks.per_second, "values": list(peaks.values)}


def decode[T](data: Json, convert: Callable[[Json], T]) -> T:
    """形の合わない JSON は ValueError にそろえる（壊れた生成物は作り直す判断に使う）。"""
    try:
        return convert(data)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise ValueError(f"生成物の形が不正です: {e}") from e
