"""ffprobe の JSON 出力 → ProbeResult。"""

from datetime import datetime
from fractions import Fraction
from typing import Any

from vidcut.domain.models import MediaInfo
from vidcut.pipeline.ports import ProbeResult, UnsupportedMediaError

# 公称と平均のフレームレートがこれ以上離れていれば可変フレームレートとみなす
_VFR_TOLERANCE = 0.01


def parse_probe(data: dict[str, Any]) -> ProbeResult:
    try:
        return _parse(data)
    except UnsupportedMediaError:
        raise
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        raise UnsupportedMediaError(f"録画ファイルの情報を読み取れません: {e}") from e


def _parse(data: dict[str, Any]) -> ProbeResult:
    streams = data["streams"]
    if not isinstance(streams, list):
        raise TypeError("streams が配列ではありません")
    video = _first_stream(streams, "video", "映像")
    audio = _first_stream(streams, "audio", "音声")
    media = _media_info(video, audio)
    return ProbeResult(
        media=media,
        duration_ms=_audio_end_ms(audio, data["format"]),
        recorded_at=_recorded_at(data["format"].get("tags") or {}),
    )


def _first_stream(streams: list[dict[str, Any]], kind: str, label: str) -> dict[str, Any]:
    for stream in streams:
        is_cover_art = (stream.get("disposition") or {}).get("attached_pic") == 1
        if stream.get("codec_type") == kind and not is_cover_art:
            return stream
    raise UnsupportedMediaError(f"{label}のトラックがありません")


def _media_info(video: dict[str, Any], audio: dict[str, Any]) -> MediaInfo:
    nominal = _rate(video.get("r_frame_rate"))
    average = _rate(video.get("avg_frame_rate")) or nominal
    if average is None:
        raise ValueError("フレームレートが分かりません")
    is_vfr = nominal is not None and abs(nominal - average) / nominal > _VFR_TOLERANCE
    return MediaInfo(
        width=int(video["width"]),
        height=int(video["height"]),
        is_vfr=is_vfr,
        avg_fps=float(average),
        audio_rate=int(audio["sample_rate"]),
    )


def _rate(value: str | None) -> Fraction | None:
    """「60/1」形式のフレームレート。「0/0」など不明な値は None。"""
    if not value:
        return None
    numerator, _, denominator = value.partition("/")
    if int(denominator or 1) == 0 or int(numerator) <= 0:
        return None
    return Fraction(int(numerator), int(denominator or 1))


def _audio_end_ms(audio: dict[str, Any], container: dict[str, Any]) -> int:
    """音声の終わり = 開始時刻 + 長さ。長さがストリームにない形式はコンテナの長さを使う。"""
    if audio.get("duration") is None:
        end_s = float(container["duration"])
    else:
        end_s = float(audio.get("start_time") or 0) + float(audio["duration"])
    end_ms = round(end_s * 1000)
    if end_ms <= 0:
        raise ValueError(f"長さが不正です: {end_s}")
    return end_ms


def _recorded_at(tags: dict[str, str]) -> datetime | None:
    value = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
