"""VoiceActivityDetector の Silero VAD による実装。"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from vidcut.adapters.ml.audio import SAMPLE_RATE, load_wav
from vidcut.domain.intervals import Interval


def speech_spans(timestamps: Sequence[Mapping[str, int]], *, rate: int) -> tuple[Interval, ...]:
    """get_speech_timestamps の結果（サンプル位置）→ ミリ秒の区間。"""
    spans = []
    for stamp in timestamps:
        start = stamp["start"] * 1000 // rate
        end = max(stamp["end"] * 1000 // rate, start + 1)
        spans.append(Interval(start, end))
    return tuple(spans)


class SileroVad:
    def __init__(self) -> None:
        self._model: Any = None

    def detect_speech(self, audio: Path) -> tuple[Interval, ...]:
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad

        if self._model is None:
            self._model = load_silero_vad()
        samples = torch.from_numpy(load_wav(audio))
        stamps = get_speech_timestamps(samples, self._model, sampling_rate=SAMPLE_RATE)
        return speech_spans(stamps, rate=SAMPLE_RATE)
