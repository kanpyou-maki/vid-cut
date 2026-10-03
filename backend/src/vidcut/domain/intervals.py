"""ミリ秒単位の半開区間 [start_ms, end_ms) と、その集合演算。"""

from collections.abc import Iterable
from dataclasses import dataclass


def require_int(name: str, value: object) -> None:
    """整数（bool を除く）であることを確かめる。API から来た値の型の混入を防ぐ多層防御。"""
    if type(value) is not int:
        raise TypeError(f"{name} は整数である必要があります: {type(value).__name__}")


@dataclass(frozen=True, order=True)
class Interval:
    """録画ファイル内の時刻の半開区間。時刻は整数ミリ秒で、長さ 0 の区間は作れない。"""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        require_int("start_ms", self.start_ms)
        require_int("end_ms", self.end_ms)
        if self.start_ms < 0:
            raise ValueError(f"start_ms は 0 以上である必要があります: {self.start_ms}")
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"end_ms は start_ms より大きい必要があります: [{self.start_ms}, {self.end_ms})"
            )

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def contains(self, ms: int) -> bool:
        return self.start_ms <= ms < self.end_ms

    def overlaps(self, other: "Interval") -> bool:
        return self.start_ms < other.end_ms and other.start_ms < self.end_ms


def merge(intervals: Iterable[Interval], gap_ms: int = 0) -> tuple[Interval, ...]:
    """区間を開始順に並べ、重なる・接する（または gap_ms 以内で隣り合う）区間を統合する。"""
    if gap_ms < 0:
        raise ValueError(f"gap_ms は 0 以上である必要があります: {gap_ms}")

    merged: list[Interval] = []
    for span in sorted(intervals):
        if merged and span.start_ms <= merged[-1].end_ms + gap_ms:
            last = merged[-1]
            merged[-1] = Interval(last.start_ms, max(last.end_ms, span.end_ms))
        else:
            merged.append(span)
    return tuple(merged)


def subtract(base: Interval, cuts: Iterable[Interval]) -> tuple[Interval, ...]:
    """base から cuts を取り除いた残りの区間を、開始順に返す。"""
    remaining: list[Interval] = []
    cursor = base.start_ms
    for cut in merge(c for c in cuts if c.overlaps(base)):
        if cut.start_ms > cursor:
            remaining.append(Interval(cursor, cut.start_ms))
        cursor = max(cursor, cut.end_ms)
    if cursor < base.end_ms:
        remaining.append(Interval(cursor, base.end_ms))
    return tuple(remaining)
