"""MediaTool の ffmpeg による実装。"""

import json
from pathlib import Path

from vidcut.adapters.media.commands import (
    MediaSettings,
    audio_args,
    mezzanine_args,
    probe_args,
    proxy_args,
)
from vidcut.adapters.media.probe import parse_probe
from vidcut.adapters.media.runner import run_capture, run_with_progress, write_atomically
from vidcut.adapters.media.waveform import compute_peaks
from vidcut.pipeline.ports import Peaks, ProbeResult, ProgressCallback, UnsupportedMediaError

_PROBE_TIMEOUT_S = 60.0


class FfmpegMediaTool:
    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        settings: MediaSettings | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._settings = settings or MediaSettings()
        self._timeout_s = timeout_s

    def probe(self, source: Path) -> ProbeResult:
        output = run_capture(probe_args(self._ffprobe, source), timeout_s=_PROBE_TIMEOUT_S)
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            raise UnsupportedMediaError(f"ffprobe の出力を読めません: {source.name}") from e
        return parse_probe(data)

    def extract_audio(self, source: Path, dest: Path) -> None:
        write_atomically(
            dest,
            lambda partial: run_with_progress(
                audio_args(self._ffmpeg, source, partial),
                total_ms=1,
                on_progress=None,
                timeout_s=self._timeout_s,
            ),
        )

    def make_proxy(
        self, source: Path, dest: Path, *, duration_ms: int, on_progress: ProgressCallback | None
    ) -> None:
        write_atomically(
            dest,
            lambda partial: run_with_progress(
                proxy_args(
                    self._ffmpeg, source, partial, duration_ms=duration_ms, settings=self._settings
                ),
                total_ms=duration_ms,
                on_progress=on_progress,
                timeout_s=self._timeout_s,
            ),
        )

    def make_mezzanine(
        self, source: Path, dest: Path, *, duration_ms: int, on_progress: ProgressCallback | None
    ) -> None:
        write_atomically(
            dest,
            lambda partial: run_with_progress(
                mezzanine_args(
                    self._ffmpeg, source, partial, duration_ms=duration_ms, settings=self._settings
                ),
                total_ms=duration_ms,
                on_progress=on_progress,
                timeout_s=self._timeout_s,
            ),
        )

    def compute_peaks(self, audio: Path, per_second: int) -> Peaks:
        return compute_peaks(audio, per_second)
