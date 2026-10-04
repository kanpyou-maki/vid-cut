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
    """フィラーの削除候補。削る区間は、フィラーの文字の位置合わせの時刻だけ。

    前後の語やチャンクの端のほうへは広げない。位置合わせは語の頭を実際より遅く置くことがあり、
    広げると、フィラーでない声を削る（Design Doc 3-2 の「試して、やめたこと」）。
    """
    words_by_chunk: dict[str, list[Token]] = {}
    for token in tokens:
        if token.text not in _PUNCTUATION:
            words_by_chunk.setdefault(token.chunk_id, []).append(token)
    suggestions: list[CutSuggestion] = []
    for chunk in chunks:
        words = words_by_chunk.get(chunk.id, [])
        for number, (start, end) in enumerate(_filler_ranges(words, min_gap_ms)):
            filler = words[start:end]
            text = "".join(t.text for t in filler)
            suggestions.append(
                CutSuggestion(
                    id=f"{chunk.id}-filler-{number}",
                    recording_id=chunk.recording_id,
                    span=_aligned_span(filler),
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
    starts, ends = _word_boundaries(words)
    ranges: list[tuple[int, int]] = []
    for match in _FILLERS.finditer(text):
        # トークンの途中で始まる・終わる一致は、時刻が分からないので候補にしない
        if match.start() not in starts or match.end() not in ends:
            continue
        start, end = starts[match.start()], ends[match.end()]
        if _pause_before(words, start, min_gap_ms) and _pause_after(words, end, min_gap_ms):
            ranges.append((start, end))
    return ranges


def _word_boundaries(words: Sequence[Token]) -> tuple[dict[int, int], dict[int, int]]:
    """つなげた文字列の中の位置 → 語の添字（その位置で始まる語と、その位置で終わる語の次）。

    トークンは複数の文字を持つことがあるので、文字の位置をそのまま語の添字には使えない。
    """
    starts: dict[int, int] = {}
    ends: dict[int, int] = {}
    offset = 0
    for index, token in enumerate(words):
        starts[offset] = index
        offset += len(token.text)
        ends[offset] = index + 1
    return starts, ends


def _aligned_span(filler: Sequence[Token]) -> Interval:
    # 位置合わせの時刻は、文字の順と前後することがある。いちばん早い開始といちばん遅い終了を取る
    return Interval(
        min(token.span.start_ms for token in filler),
        max(token.span.end_ms for token in filler),
    )


def _pause_before(words: Sequence[Token], index: int, min_gap_ms: int) -> bool:
    return index == 0 or words[index].span.start_ms - words[index - 1].span.end_ms >= min_gap_ms


def _pause_after(words: Sequence[Token], end: int, min_gap_ms: int) -> bool:
    return end == len(words) or words[end].span.start_ms - words[end - 1].span.end_ms >= min_gap_ms
