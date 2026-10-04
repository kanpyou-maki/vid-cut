"""残す区間・フレームへの丸め・出力時刻への変換（Design Doc 3-4・4 章）。"""

from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from vidcut.domain.intervals import Interval, merge, require_int, subtract
from vidcut.domain.models import Token

DEFAULT_PAD_BEFORE_MS = 150
DEFAULT_PAD_AFTER_MS = 250
# 文の終わりのあとの余白。仮の値（ユーザーがプレビューで聞いて決める。M8）
DEFAULT_PAD_AFTER_SENTENCE_MS = 500
SENTENCE_END_CHARS = frozenset("。？！?!")
MAX_PAD_MS = 2_000


@dataclass(frozen=True)
class KeepPadding:
    """残す発話の前・後ろ・文の終わりのあとに付ける余白。利用者が設定で変える（Design Doc 3-4）。"""

    before_ms: int = DEFAULT_PAD_BEFORE_MS
    after_ms: int = DEFAULT_PAD_AFTER_MS
    after_sentence_ms: int = DEFAULT_PAD_AFTER_SENTENCE_MS

    def __post_init__(self) -> None:
        for name in ("before_ms", "after_ms", "after_sentence_ms"):
            value = getattr(self, name)
            # bool は int の一種なので、型そのものを確かめる
            if type(value) is not int or not 0 <= value <= MAX_PAD_MS:
                raise ValueError(
                    f"余白は 0〜{MAX_PAD_MS} の整数（ミリ秒）である必要があります: {name}={value!r}"
                )


def keep_ranges(
    duration_ms: int,
    cuts: Iterable[Interval],
    silences: Iterable[Interval],
    pad_before_ms: int = DEFAULT_PAD_BEFORE_MS,
    pad_after_ms: int = DEFAULT_PAD_AFTER_MS,
    *,
    sentence_pauses: Iterable[Interval] = (),
    pad_after_sentence_ms: int | None = None,
) -> tuple[Interval, ...]:
    """録画ファイルの残す区間を返す。

    削除区間を除いた残りの前後に余白を付ける。余白は隣の無音区間の中にだけ伸ばし、
    削除した発話には食い込ませない。余白で重なった区間は統合する（短い無音は残る）。

    文の終わりで終わる区間は、後ろの余白に pad_after_sentence_ms を使う（省くと pad_after_ms）。
    文の終わりかどうかは sentence_pauses（sentence_pauses 関数の結果）で決まる:
    区間の終わりがその間の中にあり、区間が文末の文字を頭から含むとき。
    """
    sentence_pad_ms = pad_after_ms if pad_after_sentence_ms is None else pad_after_sentence_ms
    if duration_ms <= 0:
        raise ValueError(f"duration_ms は正である必要があります: {duration_ms}")
    if pad_before_ms < 0 or pad_after_ms < 0 or sentence_pad_ms < 0:
        raise ValueError(
            f"余白は 0 以上である必要があります: {pad_before_ms}, {pad_after_ms}, {sentence_pad_ms}"
        )

    silence_spans = merge(silences)  # 接する無音を 1 つにまとめ、余白が境目で止まらないようにする
    pauses = tuple(sentence_pauses)
    kept = subtract(Interval(0, duration_ms), cuts)
    return merge(
        Interval(
            _pad_start(span.start_ms, silence_spans, pad_before_ms),
            _pad_end(
                span.end_ms,
                silence_spans,
                sentence_pad_ms if _ends_sentence(span, pauses) else pad_after_ms,
            ),
        )
        for span in kept
    )


def sentence_pauses(tokens: Iterable[Token], silences: Iterable[Interval]) -> tuple[Interval, ...]:
    """文の終わりの間: 文末の記号のトークンの開始から、その直後の無音の終わりまで。

    無音ごとに、その前で最後に始まるトークンを見る（無音の中で始まるトークンは数えない）。
    そのトークンが文末の記号（。？！）で終わっていれば、その無音は文の終わりのあとの間。
    削除区間には依らないので、録画ファイルごとに 1 回求めればよい。
    """
    ordered = sorted(tokens, key=lambda token: (token.span.start_ms, token.span.end_ms))
    starts = [token.span.start_ms for token in ordered]
    pauses: list[Interval] = []
    for silence in merge(silences):
        index = bisect_left(starts, silence.start_ms)
        if index == 0:
            continue
        last = ordered[index - 1]
        if last.text[-1:] in SENTENCE_END_CHARS:
            pauses.append(Interval(last.span.start_ms, silence.end_ms))
    return tuple(pauses)


def _ends_sentence(span: Interval, pauses: Sequence[Interval]) -> bool:
    return any(span.start_ms <= pause.start_ms < span.end_ms < pause.end_ms for pause in pauses)


def _pad_start(start_ms: int, silences: Sequence[Interval], pad_ms: int) -> int:
    for silence in silences:
        if silence.start_ms < start_ms <= silence.end_ms:
            return max(start_ms - pad_ms, silence.start_ms)
    return start_ms


def _pad_end(end_ms: int, silences: Sequence[Interval], pad_ms: int) -> int:
    for silence in silences:
        if silence.start_ms <= end_ms < silence.end_ms:
            return min(end_ms + pad_ms, silence.end_ms)
    return end_ms


@dataclass(frozen=True, order=True)
class FrameRange:
    """中間素材のフレーム番号の半開区間 [start_frame, end_frame)。"""

    start_frame: int
    end_frame: int

    def __post_init__(self) -> None:
        require_int("start_frame", self.start_frame)
        require_int("end_frame", self.end_frame)
        if self.start_frame < 0 or self.end_frame <= self.start_frame:
            raise ValueError(f"フレーム範囲が不正です: [{self.start_frame}, {self.end_frame})")

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame


def to_frames(spans: Iterable[Interval], fps: int) -> tuple[FrameRange, ...]:
    """開始は切り捨て・終了は切り上げでフレーム境界に丸め、重なった範囲を統合する（ADR-002）。"""
    if fps <= 0:
        raise ValueError(f"fps は正である必要があります: {fps}")

    merged: list[FrameRange] = []
    for span in sorted(spans):
        frames = FrameRange(span.start_ms * fps // 1000, -(-span.end_ms * fps // 1000))
        if merged and frames.start_frame <= merged[-1].end_frame:
            last = merged[-1]
            merged[-1] = FrameRange(last.start_frame, max(last.end_frame, frames.end_frame))
        else:
            merged.append(frames)
    return tuple(merged)


@dataclass(frozen=True)
class OutputSegment:
    """出力（カット後）のタイムラインに並ぶ 1 区間。"""

    recording_id: str
    source: Interval
    output_start_ms: int


def build_output_timeline(
    parts: Sequence[tuple[str, Sequence[Interval]]],
) -> tuple[OutputSegment, ...]:
    """(録画ファイル, 残す区間) をレクチャーの順に並べ、出力時刻の開始位置を割り当てる。"""
    segments: list[OutputSegment] = []
    offset = 0
    for recording_id, spans in parts:
        for span in spans:
            segments.append(OutputSegment(recording_id, span, offset))
            offset += span.duration_ms
    return tuple(segments)


def to_output_ms(timeline: Sequence[OutputSegment], recording_id: str, ms: int) -> int | None:
    """録画ファイル内の時刻を出力の時刻に変換する。削除された時刻なら None。"""
    for segment in timeline:
        if segment.recording_id == recording_id and segment.source.contains(ms):
            return segment.output_start_ms + (ms - segment.source.start_ms)
    return None


def output_duration_ms(timeline: Sequence[OutputSegment]) -> int:
    return sum(segment.source.duration_ms for segment in timeline)
