"""ffmpeg / ffprobe の引数リストの組み立て（シェルを使わない）。"""

from dataclasses import dataclass
from pathlib import Path

_VIDEO_ENCODER = "h264_videotoolbox"
# 最後のフレームを無限に複製し、-t で音声の終わりに切りそろえる（ADR-002、S-1 の修正）
_EXTEND_LAST_FRAME = "tpad=stop=-1:stop_mode=clone"
_COMMON = ("-nostdin", "-v", "error", "-y")
# 中身がプレイリストのファイルから、ネットワークや他のプロトコルを開かせない
_LOCAL_ONLY = ("-protocol_whitelist", "file")
_PROGRESS = ("-progress", "pipe:1", "-nostats")


@dataclass(frozen=True)
class MediaSettings:
    mezzanine_fps: int = 60
    mezzanine_quality: int = 60
    proxy_fps: int = 30
    proxy_long_side: int = 1280
    proxy_quality: int = 50
    proxy_audio_bitrate: str = "128k"

    def __post_init__(self) -> None:
        if self.mezzanine_fps <= 0 or self.proxy_fps <= 0:
            raise ValueError(f"フレームレートは正である必要があります: {self}")
        if not (1 <= self.mezzanine_quality <= 100 and 1 <= self.proxy_quality <= 100):
            raise ValueError(f"画質は 1〜100 で指定してください: {self}")
        if self.proxy_long_side < 2:
            raise ValueError(f"proxy の長辺が小さすぎます: {self.proxy_long_side}")


def probe_args(ffprobe: str, source: Path) -> list[str]:
    return [
        ffprobe, "-v", "error", *_LOCAL_ONLY, "-show_streams", "-show_format", "-of", "json",
        _abs(source),
    ]  # fmt: skip


def audio_args(ffmpeg: str, source: Path, dest: Path) -> list[str]:
    """解析用の 16kHz モノラル wav。音声の開始の遅れは先頭の無音で埋めてタイムラインにそろえる。"""
    return [
        ffmpeg, *_COMMON, *_LOCAL_ONLY, "-i", _abs(source), "-map", "0:a:0", "-vn",
        "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", _abs(dest),
    ]  # fmt: skip


def mezzanine_args(
    ffmpeg: str, source: Path, dest: Path, *, duration_ms: int, settings: MediaSettings
) -> list[str]:
    video_filter = f"fps={settings.mezzanine_fps},{_EXTEND_LAST_FRAME}"
    return [
        ffmpeg, *_COMMON, *_LOCAL_ONLY, "-i", _abs(source), "-map", "0:v:0", "-map", "0:a:0",
        "-vf", video_filter, "-t", _seconds(duration_ms),
        "-c:v", _VIDEO_ENCODER, "-q:v", str(settings.mezzanine_quality),
        "-c:a", "copy", "-movflags", "+faststart", *_PROGRESS, _abs(dest),
    ]  # fmt: skip


def proxy_args(
    ffmpeg: str, source: Path, dest: Path, *, duration_ms: int, settings: MediaSettings
) -> list[str]:
    video_filter = ",".join(
        [
            f"fps={settings.proxy_fps}",
            _EXTEND_LAST_FRAME,
            _scale_long_side(settings.proxy_long_side),
            "format=yuv420p",
        ]
    )
    return [
        ffmpeg, *_COMMON, *_LOCAL_ONLY, "-i", _abs(source), "-map", "0:v:0", "-map", "0:a:0",
        "-vf", video_filter, "-t", _seconds(duration_ms),
        "-c:v", _VIDEO_ENCODER, "-q:v", str(settings.proxy_quality),
        "-g", str(settings.proxy_fps),
        "-c:a", "aac", "-b:a", settings.proxy_audio_bitrate,
        "-movflags", "+faststart", *_PROGRESS, _abs(dest),
    ]  # fmt: skip


def _scale_long_side(long_side: int) -> str:
    """長辺を long_side 以下に縮める（拡大はしない）。幅と高さは偶数にそろえる。"""
    fit = f"trunc(min({long_side},iw)/2)*2"
    fit_height = f"trunc(min({long_side},ih)/2)*2"
    return f"scale=w='if(gte(iw,ih),{fit},-2)':h='if(gte(iw,ih),-2,{fit_height})'"


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.3f}"


def _abs(path: Path) -> str:
    """「-」で始まる名前がオプションとして解釈されないよう、絶対パスだけを渡す。"""
    if not path.is_absolute():
        raise ValueError(f"絶対パスを指定してください: {path}")
    return str(path)
