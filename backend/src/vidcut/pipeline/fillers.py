"""フィラーの検出: 辞書 + 前後の区切れ（Design Doc 3-2 段 8）。"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, SpeechChunk, Token

DEFAULT_MIN_GAP_MS = 100
DEFAULT_GUARD_MS = 50
DEFAULT_MAX_STRETCH_MS = 1_000

# 長いものを先に並べる（「えーと」を「えー」より優先する）。ambiguous は内容語にもなる語で、
# フィラーと続いているときと、チャンクがそれだけのときに限って候補にする
_PATTERN = re.compile(
    r"(?P<filler>えー+っ?と|えっと|えー+|あのー+|うー+ん|んー+|あー+)"
    r"|(?P<ambiguous>(?:まあ|その|あの)ー*)"
)
_PUNCTUATION = frozenset("、。，．,.!?！？「」『』…・〜")


@dataclass(frozen=True)
class _Match:
    """辞書に一致した範囲。start と end は、句読点を除いた文字（words）の添字 [start, end)。"""

    start: int
    end: int
    ambiguous: bool


@dataclass(frozen=True)
class _CutLimits:
    guard_ms: int  # 前後の語の端から残す余裕
    max_stretch_ms: int  # 位置合わせの時刻から広げる上限


@dataclass(frozen=True)
class _Words:
    """チャンクのトークンのうち、句読点を除いたもの（words）と、その並びの中の区切れ。"""

    tokens: Sequence[Token]  # チャンクのトークン（句読点を含む）
    positions: Sequence[int]  # words[i] の、tokens の中の位置
    words: Sequence[Token]
    min_gap_ms: int

    @classmethod
    def of(cls, tokens: Sequence[Token], min_gap_ms: int) -> "_Words":
        positions = [i for i, token in enumerate(tokens) if token.text not in _PUNCTUATION]
        return cls(tokens, positions, [tokens[i] for i in positions], min_gap_ms)

    def breaks_before(self, index: int) -> bool:
        """words[index] の前が区切れているか: チャンクの頭、句読点が挟まる、間があく。"""
        if index == 0:
            return True
        previous, current = self.positions[index - 1], self.positions[index]
        if current - previous > 1:  # 間に句読点のトークンがある
            return True
        gap = self.tokens[current].span.start_ms - self.tokens[previous].span.end_ms
        return gap >= self.min_gap_ms

    def breaks_after(self, end: int) -> bool:
        """words[end - 1] の後ろが区切れているか（チャンクの終わりも可）。"""
        return end == len(self.positions) or self.breaks_before(end)

    def text(self, start: int, end: int) -> str:
        """words[start:end] の文字（間の句読点を含む）。"""
        first, last = self.positions[start], self.positions[end - 1]
        return "".join(token.text for token in self.tokens[first : last + 1])


def detect_fillers(
    chunks: Sequence[SpeechChunk],
    tokens: Sequence[Token],
    *,
    min_gap_ms: int = DEFAULT_MIN_GAP_MS,
    guard_ms: int = DEFAULT_GUARD_MS,
    max_stretch_ms: int = DEFAULT_MAX_STRETCH_MS,
) -> tuple[CutSuggestion, ...]:
    """フィラーの削除候補。続いたフィラーは 1 つにまとめる。

    削除する区間は、前の語の終わりの guard_ms あとから、次の語の頭の guard_ms 手前まで
    （位置合わせは、伸ばした声に短い時刻しか付けないことがあるため。Design Doc 3-2）。
    ただし、位置合わせの時刻から max_stretch_ms を超えては広げない
    （文字のない長い区間には、書き起こされなかった発話があるかもしれない）。
    """
    if guard_ms < 0:
        raise ValueError(f"guard_ms は 0 以上である必要があります: {guard_ms}")
    if max_stretch_ms < 0:
        raise ValueError(f"max_stretch_ms は 0 以上である必要があります: {max_stretch_ms}")
    limits = _CutLimits(guard_ms, max_stretch_ms)
    by_chunk: dict[str, list[Token]] = {}
    for token in tokens:
        by_chunk.setdefault(token.chunk_id, []).append(token)
    suggestions: list[CutSuggestion] = []
    for chunk in chunks:
        words = _Words.of(by_chunk.get(chunk.id, []), min_gap_ms)
        for number, (start, end) in enumerate(_filler_ranges(words)):
            suggestions.append(
                CutSuggestion(
                    id=f"{chunk.id}-filler-{number}",
                    recording_id=chunk.recording_id,
                    span=_cut_span(chunk, words.words, start, end, limits),
                    kind=CutKind.FILLER,
                    reason=f"フィラー「{words.text(start, end)}」",
                )
            )
    return tuple(suggestions)


def _filler_ranges(words: _Words) -> list[tuple[int, int]]:
    """フィラーに当たる words の添字の範囲 [start, end)。続いたものは 1 つの範囲にまとめる。"""
    spoken = words.words
    text = "".join(token.text for token in spoken)
    starts, ends = _word_boundaries(spoken)
    matches = [
        _Match(starts[m.start()], ends[m.end()], m.lastgroup == "ambiguous")
        for m in _PATTERN.finditer(text)
        # トークンの途中で始まる・終わる一致は、時刻が分からないので候補にしない
        if m.start() in starts and m.end() in ends
    ]
    ranges: list[tuple[int, int]] = []
    index = 0
    while index < len(matches):
        last = _run_end(matches, index, words)
        if last is None:
            index += 1
            continue
        run = matches[index : last + 1]
        whole_chunk = run[0].start == 0 and run[-1].end == len(spoken)
        if whole_chunk or not all(match.ambiguous for match in run):
            ranges.append((run[0].start, run[-1].end))
        index = last + 1
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


def _run_end(matches: Sequence[_Match], first: int, words: _Words) -> int | None:
    """matches[first] から続く一致のうち、前後が区切れているまとまりの、最後の添字。なければ None。

    まとまりの内側（一致どうしが隣り合うところ）は、区切れていなくてよい。
    前が区切れていなくても、チャンクの終わりまで続くフィラーは候補にする（後ろは無音。
    位置合わせは、フィラーの前の間を詰めてしまうことがある）。内容語にもなる語から始まるものは除く。
    """
    opens = words.breaks_before(matches[first].start)
    if not opens and matches[first].ambiguous:
        return None
    total = len(words.positions)
    last: int | None = None
    index = first
    while True:
        if matches[index].end == total or (opens and words.breaks_after(matches[index].end)):
            last = index
        following = index + 1
        if following == len(matches) or matches[following].start != matches[index].end:
            return last
        index = following


def _cut_span(
    chunk: SpeechChunk, words: Sequence[Token], start: int, end: int, limits: _CutLimits
) -> Interval:
    """words[start:end] を消すときの区間。位置合わせの時刻より狭くはしない。"""
    # 位置合わせの時刻は、文字の順と前後することがある。フィラーの文字の、いちばん早い開始と
    # いちばん遅い終了を基準にする（開始 < 終了が保たれる）
    aligned_start = min(word.span.start_ms for word in words[start:end])
    aligned_end = max(word.span.end_ms for word in words[start:end])
    if start == 0:
        cut_start = min(chunk.span.start_ms, aligned_start)
    else:
        cut_start = min(words[start - 1].span.end_ms + limits.guard_ms, aligned_start)
    if end == len(words):
        cut_end = max(chunk.span.end_ms, aligned_end)
    else:
        cut_end = max(words[end].span.start_ms - limits.guard_ms, aligned_end)
    return Interval(
        max(cut_start, aligned_start - limits.max_stretch_ms),
        min(cut_end, aligned_end + limits.max_stretch_ms),
    )
