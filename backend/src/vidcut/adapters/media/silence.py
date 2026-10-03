"""silencedetect + ametadata の出力 → 無音区間。"""

from vidcut.domain.intervals import Interval

_START = "lavfi.silence_start="
_END = "lavfi.silence_end="


def parse_silences(stdout: str, *, duration_ms: int) -> tuple[Interval, ...]:
    """開始と終了の組を区間にする。終わりまで続く無音は duration_ms で閉じる。"""
    pairs: list[tuple[int, int]] = []
    start_ms: int | None = None
    for line in stdout.splitlines():
        if line.startswith(_START):
            start_ms = _to_ms(line[len(_START) :])
        elif line.startswith(_END) and start_ms is not None:
            pairs.append((start_ms, _to_ms(line[len(_END) :])))
            start_ms = None
    if start_ms is not None:
        pairs.append((start_ms, duration_ms))
    clamped = ((max(start, 0), min(end, duration_ms)) for start, end in pairs)
    return tuple(Interval(start, end) for start, end in clamped if end > start)


def _to_ms(value: str) -> int:
    return round(float(value.strip()) * 1000)
