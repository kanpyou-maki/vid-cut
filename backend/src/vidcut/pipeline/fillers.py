"""フィラーの検出: 辞書 + 前後の無音（Design Doc 3-2 段 8）。"""

import re
from collections.abc import Sequence

from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, SpeechChunk, Token

DEFAULT_MIN_GAP_MS = 100

# 長いものを先に並べる（「えーと」を「えー」より優先する）
_FILLERS = re.compile(r"えー+っ?と|えっと|えー+|あのー+|うー+ん|んー+|あー+")
# 内容語にもなる語。チャンク全体がこの語だけのときに限って候補にする
_AMBIGUOUS = re.compile(r"(?:まあ|その|あの)ー*")
_PUNCTUATION = frozenset("、。，．,.!?！？「」『』…・〜")


def detect_fillers(
    chunks: Sequence[SpeechChunk],
    tokens: Sequence[Token],
    *,
    min_gap_ms: int = DEFAULT_MIN_GAP_MS,
) -> tuple[CutSuggestion, ...]:
    suggestions: list[CutSuggestion] = []
    for chunk in chunks:
        words = [t for t in tokens if t.chunk_id == chunk.id and t.text not in _PUNCTUATION]
        for number, (start, end) in enumerate(_filler_ranges(words, min_gap_ms)):
            filler = words[start:end]
            text = "".join(t.text for t in filler)
            suggestions.append(
                CutSuggestion(
                    id=f"{chunk.id}-filler-{number}",
                    recording_id=chunk.recording_id,
                    span=Interval(filler[0].span.start_ms, filler[-1].span.end_ms),
                    kind=CutKind.FILLER,
                    reason=f"フィラー「{text}」",
                )
            )
    return tuple(suggestions)


def _filler_ranges(words: Sequence[Token], min_gap_ms: int) -> list[tuple[int, int]]:
    """フィラーに当たる words の添字の範囲 [start, end)。"""
    text = "".join(t.text for t in words)
    if text and _AMBIGUOUS.fullmatch(text):
        return [(0, len(words))]
    return [
        (m.start(), m.end())
        for m in _FILLERS.finditer(text)
        if _pause_before(words, m.start(), min_gap_ms) and _pause_after(words, m.end(), min_gap_ms)
    ]


def _pause_before(words: Sequence[Token], index: int, min_gap_ms: int) -> bool:
    return index == 0 or words[index].span.start_ms - words[index - 1].span.end_ms >= min_gap_ms


def _pause_after(words: Sequence[Token], end: int, min_gap_ms: int) -> bool:
    return end == len(words) or words[end].span.start_ms - words[end - 1].span.end_ms >= min_gap_ms
