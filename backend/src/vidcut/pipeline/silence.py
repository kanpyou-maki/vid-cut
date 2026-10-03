"""無音区間と発話チャンクの決定（Design Doc 3-2 段 5）。"""

from collections.abc import Iterable

from vidcut.domain.intervals import Interval, merge, subtract


def find_silences(
    volume_silences: Iterable[Interval], speech: Iterable[Interval], min_ms: int
) -> tuple[Interval, ...]:
    """音量で無音、かつ VAD が発話としなかった部分のうち、min_ms 以上続くもの。

    無音は削除候補になるため、両方が「発話なし」とした部分だけを無音にする（誤削除を避ける）。
    """
    if min_ms < 0:
        raise ValueError(f"min_ms は 0 以上である必要があります: {min_ms}")
    speech_spans = merge(speech)
    pieces = (piece for quiet in merge(volume_silences) for piece in subtract(quiet, speech_spans))
    return tuple(piece for piece in pieces if piece.duration_ms >= min_ms)


def split_chunks(
    duration_ms: int, silences: Iterable[Interval], min_ms: int
) -> tuple[Interval, ...]:
    """無音で区切った残りを発話チャンクにする。min_ms 未満の断片は捨てる。"""
    if duration_ms <= 0:
        raise ValueError(f"duration_ms は正である必要があります: {duration_ms}")
    gaps = subtract(Interval(0, duration_ms), silences)
    return tuple(gap for gap in gaps if gap.duration_ms >= min_ms)
