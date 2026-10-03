"""無音区間と発話チャンクの決定（Design Doc 3-2 段 5）。"""

from collections.abc import Iterable

from vidcut.domain.intervals import Interval, merge, subtract

# probe の長さは、音声の先頭の空白（AAC の priming。約 44ms）を二重に数えるぶん長い
END_TOLERANCE_MS = 100


def extend_to_end(
    silences: Iterable[Interval], duration_ms: int, tolerance_ms: int = END_TOLERANCE_MS
) -> tuple[Interval, ...]:
    """音声の終わりまで続く無音を、録画ファイルの終わりまで延ばす。

    解析用の音声は録画ファイルの長さ（probe の値）より少し早く終わる。延ばさないと、最後の無音と
    録画ファイルの終わりの間に、発話でも無音でもない数十 ms の断片が残り、書き出しに入ってしまう。
    """
    if duration_ms <= 0:
        raise ValueError(f"duration_ms は正である必要があります: {duration_ms}")
    if tolerance_ms < 0:
        raise ValueError(f"tolerance_ms は 0 以上である必要があります: {tolerance_ms}")
    spans = merge(silences)
    if not spans:
        return ()
    last = spans[-1]
    if duration_ms - tolerance_ms <= last.end_ms < duration_ms:
        return (*spans[:-1], Interval(last.start_ms, duration_ms))
    return spans


def find_silences(
    volume_silences: Iterable[Interval], speech: Iterable[Interval], min_ms: int
) -> tuple[Interval, ...]:
    """音量による無音から、その内側に収まる VAD の発話区間を除き、min_ms 以上残った部分。

    無音は削除候補になるため、無音の中に紛れた小声の発話は残す。一方、VAD の発話区間は
    前後に余韻を含み、句の間の短い無音もまたぐため、無音の端にかかる区間は使わない
    （使うと無音が縮み、チャンクがつながってしまう。検証素材で確認）。
    """
    if min_ms < 0:
        raise ValueError(f"min_ms は 0 以上である必要があります: {min_ms}")
    speech_spans = merge(speech)
    pieces = (
        piece
        for quiet in merge(volume_silences)
        for piece in subtract(quiet, [s for s in speech_spans if _strictly_inside(s, quiet)])
    )
    return tuple(piece for piece in pieces if piece.duration_ms >= min_ms)


def _strictly_inside(span: Interval, outer: Interval) -> bool:
    return outer.start_ms < span.start_ms and span.end_ms < outer.end_ms


def split_chunks(
    duration_ms: int, silences: Iterable[Interval], min_ms: int
) -> tuple[Interval, ...]:
    """無音で区切った残りを発話チャンクにする。min_ms 未満の断片は捨てる。"""
    if duration_ms <= 0:
        raise ValueError(f"duration_ms は正である必要があります: {duration_ms}")
    gaps = subtract(Interval(0, duration_ms), silences)
    return tuple(gap for gap in gaps if gap.duration_ms >= min_ms)
