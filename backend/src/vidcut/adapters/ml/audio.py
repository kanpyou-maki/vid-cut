"""解析用の wav（16kHz・モノラル・16bit）の読み込み。"""

import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

from vidcut.domain.intervals import Interval

SAMPLE_RATE = 16_000
_FULL_SCALE = 32768.0

Audio = npt.NDArray[np.float32]


def load_wav(path: Path) -> Audio:
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError(f"16kHz・モノラル・16bit の wav が必要です: {path.name}")
        frames = wav.readframes(wav.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32)
    return samples / np.float32(_FULL_SCALE)


def slice_ms(audio: Audio, span: Interval) -> Audio:
    return audio[span.start_ms * SAMPLE_RATE // 1000 : span.end_ms * SAMPLE_RATE // 1000]
