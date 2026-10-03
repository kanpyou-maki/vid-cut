"""解析の結果（analysis.json）。言い直しの判定（M4）と API（M6）が読む。"""

from dataclasses import dataclass

from vidcut.domain.models import CutSuggestion, ReviewMark, Silence, SpeechChunk, Token
from vidcut.pipeline import serialization as ser
from vidcut.pipeline.ports import ArtifactStore

ANALYSIS_FILE = "analysis.json"


@dataclass(frozen=True)
class Analysis:
    recording_id: str
    silences: tuple[Silence, ...]
    chunks: tuple[SpeechChunk, ...]
    tokens: tuple[Token, ...]
    suggestions: tuple[CutSuggestion, ...]  # 無音とフィラー（言い直し系は判定ジョブが作る）
    review_marks: tuple[ReviewMark, ...]


def save_analysis(store: ArtifactStore, analysis: Analysis) -> None:
    store.write_json(
        analysis.recording_id,
        ANALYSIS_FILE,
        {
            "silences": [ser.span_to(s.span) for s in analysis.silences],
            "chunks": [ser.chunk_to(c) for c in analysis.chunks],
            "tokens": [ser.token_to(t) for t in analysis.tokens],
            "suggestions": [ser.suggestion_to(s) for s in analysis.suggestions],
            "review_marks": [ser.mark_to(m) for m in analysis.review_marks],
        },
    )


def load_analysis(store: ArtifactStore, recording_id: str) -> Analysis | None:
    """まだ解析していなければ None。形が壊れていれば ValueError。"""
    data = store.read_json(recording_id, ANALYSIS_FILE)
    if data is None:
        return None
    rid = recording_id
    return ser.decode(
        data,
        lambda d: Analysis(
            recording_id=rid,
            silences=tuple(ser.silence_from(s, rid) for s in d["silences"]),
            chunks=tuple(ser.chunk_from(c, rid) for c in d["chunks"]),
            tokens=tuple(ser.token_from(t, rid) for t in d["tokens"]),
            suggestions=tuple(ser.suggestion_from(s, rid) for s in d["suggestions"]),
            review_marks=tuple(ser.mark_from(m, rid) for m in d["review_marks"]),
        ),
    )
