"""ffmpeg / ffprobe の引数リストの組み立て（シェルを使わない）。"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vidcut.pipeline.ports import MediaClip

_VIDEO_ENCODER = "h264_videotoolbox"
# 最後のフレームを無限に複製し、-t で音声の終わりに切りそろえる（ADR-002、S-1 の修正）
_EXTEND_LAST_FRAME = "tpad=stop=-1:stop_mode=clone"
# 音声の開始の遅れを先頭の無音で埋め、音声の時刻をタイムラインの 0 秒にそろえる
_FILL_LEADING_GAP = "aresample=async=1:first_pts=0"
_RESET_VIDEO_TIME = "setpts=PTS-STARTPTS"
_RESET_AUDIO_TIME = "asetpts=PTS-STARTPTS"
_COMMON = ("-nostdin", "-v", "error", "-y")
# 中身がプレイリストのファイルから、ネットワークや他のプロトコルを開かせない
_LOCAL_ONLY = ("-protocol_whitelist", "file")
_PROGRESS = ("-progress", "pipe:1", "-nostats")
# 打ち切りまでの時間 = 基本 + 録画の長さ × 倍率。中間素材は実時間の 0.8 倍ほどかかる（ADR-002）
_BASE_TIMEOUT_S = 300
_TIMEOUT_PER_MEDIA_SECOND = 4


@dataclass(frozen=True)
class MediaSettings:
    mezzanine_fps: int = 60
    mezzanine_quality: int = 60
    proxy_fps: int = 30
    proxy_long_side: int = 1280
    proxy_quality: int = 50
    proxy_audio_bitrate: str = "128k"
    export_quality: int = 60
    export_audio_bitrate: str = "192k"

    def __post_init__(self) -> None:
        if self.mezzanine_fps <= 0 or self.proxy_fps <= 0:
            raise ValueError(f"フレームレートは正である必要があります: {self}")
        qualities = (self.mezzanine_quality, self.proxy_quality, self.export_quality)
        if not all(1 <= quality <= 100 for quality in qualities):
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
        "-af", _FILL_LEADING_GAP, "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", _abs(dest),
    ]  # fmt: skip


def silence_args(ffmpeg: str, audio: Path, *, threshold_db: float, min_ms: int) -> list[str]:
    """音量による無音検出。検出結果は ametadata で標準出力に出す（-v error でも読めるように）。"""
    detect = f"silencedetect=noise={threshold_db:g}dB:duration={_seconds(min_ms)}"
    return [
        ffmpeg, *_COMMON, *_LOCAL_ONLY, "-i", _abs(audio), "-map", "0:a:0",
        "-af", f"{detect},ametadata=mode=print:file=-", "-f", "null", "-",
    ]  # fmt: skip


def timeout_for(duration_ms: int) -> float:
    return _BASE_TIMEOUT_S + duration_ms / 1000 * _TIMEOUT_PER_MEDIA_SECOND


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


def export_args(
    ffmpeg: str, clips: Sequence[MediaClip], dest: Path, *, fps: int, settings: MediaSettings
) -> list[str]:
    """中間素材から clips を切り出してつなぐ（trim / atrim / concat。Design Doc 3-4）。"""
    if not clips:
        raise ValueError("残す区間がありません")
    if fps <= 0:
        raise ValueError(f"fps は正である必要があります: {fps}")
    sources = list(dict.fromkeys(clip.source for clip in clips))
    inputs = [arg for source in sources for arg in (*_LOCAL_ONLY, "-i", _abs(source))]
    return [
        ffmpeg, *_COMMON, *inputs, "-filter_complex", _export_graph(clips, sources, fps),
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", _VIDEO_ENCODER, "-q:v", str(settings.export_quality),
        "-c:a", "aac", "-b:a", settings.export_audio_bitrate,
        "-movflags", "+faststart", *_PROGRESS, _abs(dest),
    ]  # fmt: skip


def export_decoded_ms(clips: Sequence[MediaClip], *, fps: int) -> int:
    """書き出しで ffmpeg が読む長さ。各中間素材を、最後に使うフレームまで読む。"""
    last_frames: dict[Path, int] = {}
    for clip in clips:
        last_frames[clip.source] = max(last_frames.get(clip.source, 0), clip.frames.end_frame)
    return sum(-(-frames * 1000 // fps) for frames in last_frames.values())


def _export_graph(clips: Sequence[MediaClip], sources: Sequence[Path], fps: int) -> str:
    """クリップ k は、中間素材を分けた [s{k}v] / [s{k}a] から切り出し、[c{k}v] / [c{k}a] に出す。"""
    chains: list[str] = []
    for input_index, source in enumerate(sources):
        used = [k for k, clip in enumerate(clips) if clip.source == source]
        video_outputs = "".join(f"[s{k}v]" for k in used)
        audio_outputs = "".join(f"[s{k}a]" for k in used)
        chains.append(f"[{input_index}:v:0]split={len(used)}{video_outputs}")
        chains.append(f"[{input_index}:a:0]{_FILL_LEADING_GAP},asplit={len(used)}{audio_outputs}")
    for k, clip in enumerate(clips):
        frames = clip.frames
        # 映像はフレーム番号で切る（時刻の小数で切ると、境界のフレームが丸めの誤差で落ちうる）
        chains.append(
            f"[s{k}v]trim=start_frame={frames.start_frame}:end_frame={frames.end_frame},"
            f"{_RESET_VIDEO_TIME}[c{k}v]"
        )
        chains.append(
            f"[s{k}a]atrim=start={frames.start_frame / fps:.6f}:end={frames.end_frame / fps:.6f},"
            f"{_RESET_AUDIO_TIME}[c{k}a]"
        )
    joined = "".join(f"[c{k}v][c{k}a]" for k in range(len(clips)))
    chains.append(f"{joined}concat=n={len(clips)}:v=1:a=1[joinedv][outa]")
    # concat は時刻をマイクロ秒単位で出す。固定フレームレートの時刻に直してから符号化する
    chains.append(f"[joinedv]fps={fps}[outv]")
    return ";".join(chains)


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
