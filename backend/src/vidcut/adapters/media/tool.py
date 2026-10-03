"""MediaTool の ffmpeg による実装。"""

import json
from collections.abc import Sequence
from pathlib import Path

from vidcut.adapters.media.commands import (
    MediaSettings,
    audio_args,
    export_args,
    export_decoded_ms,
    mezzanine_args,
    probe_args,
    proxy_args,
    silence_args,
    timeout_for,
)
from vidcut.adapters.media.probe import parse_probe
from vidcut.adapters.media.runner import run_capture, run_with_progress, write_atomically
from vidcut.adapters.media.silence import parse_silences
from vidcut.adapters.media.waveform import compute_peaks, wav_duration_ms
from vidcut.domain.intervals import Interval
from vidcut.pipeline.ports import (
    MediaClip,
    Peaks,
    ProbeResult,
    ProgressCallback,
    UnsupportedMediaError,
)

_PROBE_TIMEOUT_S = 60.0
# 音声だけの処理は速い（6 分の素材で 1 秒未満）。長さが分からない段の上限
_AUDIO_TIMEOUT_S = 600.0


class FfmpegMediaTool:
    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        settings: MediaSettings | None = None,
    ) -> None:
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._settings = settings or MediaSettings()

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
                timeout_s=_AUDIO_TIMEOUT_S,
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
                timeout_s=timeout_for(duration_ms),
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
                timeout_s=timeout_for(duration_ms),
            ),
        )

    def export_mp4(
        self,
        clips: Sequence[MediaClip],
        dest: Path,
        *,
        fps: int,
        on_progress: ProgressCallback | None,
    ) -> None:
        output_frames = sum(clip.frames.duration_frames for clip in clips)
        write_atomically(
            dest,
            lambda partial: run_with_progress(
                export_args(self._ffmpeg, clips, partial, fps=fps, settings=self._settings),
                total_ms=output_frames * 1000 // fps,
                on_progress=on_progress,
                timeout_s=timeout_for(export_decoded_ms(clips, fps=fps)),
            ),
        )

    def compute_peaks(self, audio: Path, per_second: int) -> Peaks:
        return compute_peaks(audio, per_second)

    def detect_silences(
        self, audio: Path, *, threshold_db: float, min_ms: int
    ) -> tuple[Interval, ...]:
        args = silence_args(self._ffmpeg, audio, threshold_db=threshold_db, min_ms=min_ms)
        output = run_capture(args, timeout_s=_AUDIO_TIMEOUT_S)
        return parse_silences(output, duration_ms=wav_duration_ms(audio))
