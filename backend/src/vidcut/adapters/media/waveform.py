"""16bit モノラル wav → 波形のピーク値（画面の波形表示用）。"""

import array
import sys
import wave
from pathlib import Path

from vidcut.pipeline.ports import Peaks

_FULL_SCALE = 32768
_DIGITS = 3
_BUCKETS_PER_READ = 1000


def compute_peaks(audio: Path, per_second: int) -> Peaks:
    with wave.open(str(audio), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(f"16bit モノラルの wav が必要です: {audio.name}")
        rate = wav.getframerate()
        if per_second <= 0 or rate % per_second != 0:
            raise ValueError(f"1 秒あたりの個数はサンプルレート {rate} の約数にしてください")
        bucket = rate // per_second
        values: list[float] = []
        while chunk := wav.readframes(bucket * _BUCKETS_PER_READ):
            values.extend(_bucket_peaks(chunk, bucket))
    return Peaks(per_second=per_second, values=tuple(values))


def wav_duration_ms(audio: Path) -> int:
    with wave.open(str(audio), "rb") as wav:
        return round(wav.getnframes() * 1000 / wav.getframerate())


def _bucket_peaks(chunk: bytes, bucket: int) -> list[float]:
    samples = array.array("h", chunk)
    if sys.byteorder == "big":
        samples.byteswap()  # wav はリトルエンディアン
    return [
        round(max(abs(s) for s in samples[i : i + bucket]) / _FULL_SCALE, _DIGITS)
        for i in range(0, len(samples), bucket)
    ]
