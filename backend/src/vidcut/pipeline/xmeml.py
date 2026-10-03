"""Premiere XML（FCP7 xmeml v4）の生成（Design Doc 3-4）。

映像 1 トラックと音声 2 トラック（ステレオの左右）に、中間素材を参照するクリップを計画の順に並べる。
要素の並びはスパイク S-1 で Premiere Pro に読み込ませて確かめた形のまま（ADR-002）。
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from vidcut.pipeline.export import ExportClip, ExportPlan

_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
_AUDIO_TRACKS = (1, 2)
_AUDIO_DEPTH = "16"
# XML 1.0 に書けない文字（タブ・改行以外の制御文字など）。エスケープしても不正な XML になる
_NOT_XML_CHARS = re.compile("[^\\t\\n\\r\\x20-\\ud7ff\\ue000-\\ufffd\\U00010000-\\U0010ffff]")


@dataclass(frozen=True)
class XmemlFile:
    """クリップが参照する中間素材。name は Premiere に表示する名前。"""

    name: str
    path: Path
    duration_frames: int
    width: int
    height: int
    audio_rate: int


def build_xmeml(title: str, plan: ExportPlan, files: Mapping[str, XmemlFile]) -> str:
    """files は録画ファイルの id → 中間素材。シーケンスの解像度は最初のクリップに合わせる。"""
    if not plan.clips:
        raise ValueError("残す区間がありません")
    _validate(plan, files)
    layout = _Layout(plan, files)

    root = ET.Element("xmeml", version="4")
    sequence = ET.SubElement(root, "sequence", id="seq-1")
    _text(sequence, "name", title)
    _text(sequence, "duration", plan.total_frames)
    _rate(sequence, plan.fps)
    timecode = ET.SubElement(sequence, "timecode")
    _rate(timecode, plan.fps)
    _text(timecode, "string", "00:00:00:00")
    _text(timecode, "frame", 0)
    _text(timecode, "displayformat", "NDF")
    media = ET.SubElement(sequence, "media")
    _video_section(ET.SubElement(media, "video"), layout)
    _audio_section(ET.SubElement(media, "audio"), layout)
    return _HEADER + ET.tostring(root, encoding="unicode")


@dataclass(frozen=True)
class _Placed:
    index: int  # トラック内の番号（1 始まり）
    clip: ExportClip
    start: int  # シーケンス上の開始フレーム
    source: XmemlFile
    file_id: str


class _Layout:
    """クリップの並び: シーケンス上の開始フレームと、参照する中間素材・file 要素の id。"""

    def __init__(self, plan: ExportPlan, files: Mapping[str, XmemlFile]) -> None:
        self.fps = plan.fps
        self.first = files[plan.clips[0].recording_id]
        # 計画に最初に現れた順に file-1, file-2, ... と番号を振る
        ordered = dict.fromkeys(clip.recording_id for clip in plan.clips)
        file_ids = {rid: f"file-{number}" for number, rid in enumerate(ordered, 1)}
        placed: list[_Placed] = []
        offset = 0
        for index, clip in enumerate(plan.clips, 1):
            rid = clip.recording_id
            placed.append(_Placed(index, clip, offset, files[rid], file_ids[rid]))
            offset += clip.frames.duration_frames
        self.clips = tuple(placed)


def _video_section(video: ET.Element, layout: _Layout) -> None:
    _video_characteristics(ET.SubElement(video, "format"), layout.first, layout.fps)
    track = ET.SubElement(video, "track")
    described: set[str] = set()
    for placed in layout.clips:
        item = _clip_item(track, f"v-{placed.index}", placed, layout.fps)
        file = ET.SubElement(item, "file", id=placed.file_id)
        if placed.file_id not in described:
            # 中間素材の説明は最初の参照にだけ書き、以降は id で参照する
            described.add(placed.file_id)
            _describe_file(file, placed.source, layout.fps)
        _links(item, placed.index)


def _audio_section(audio: ET.Element, layout: _Layout) -> None:
    _text(audio, "numOutputChannels", len(_AUDIO_TRACKS))
    _audio_characteristics(ET.SubElement(audio, "format"), layout.first)
    for track_index in _AUDIO_TRACKS:
        track = ET.SubElement(audio, "track")
        for placed in layout.clips:
            item = _clip_item(track, f"a{track_index}-{placed.index}", placed, layout.fps)
            ET.SubElement(item, "file", id=placed.file_id)
            source_track = ET.SubElement(item, "sourcetrack")
            _text(source_track, "mediatype", "audio")
            _text(source_track, "trackindex", track_index)
            _links(item, placed.index)
        _text(track, "outputchannelindex", track_index)


def _validate(plan: ExportPlan, files: Mapping[str, XmemlFile]) -> None:
    for clip in plan.clips:
        source = files.get(clip.recording_id)
        if source is None:
            raise ValueError(f"中間素材の情報がありません: {clip.recording_id}")
        if not source.path.is_absolute():
            raise ValueError(f"絶対パスを指定してください: {source.path}")
        if clip.frames.end_frame > source.duration_frames:
            raise ValueError(
                f"クリップが中間素材の長さを超えています: {clip.recording_id}"
                f" [{clip.frames.start_frame}, {clip.frames.end_frame}) > {source.duration_frames}"
            )


def _clip_item(track: ET.Element, clip_id: str, placed: _Placed, fps: int) -> ET.Element:
    frames = placed.clip.frames
    item = ET.SubElement(track, "clipitem", id=clip_id)
    _text(item, "name", placed.source.name)
    _text(item, "enabled", "TRUE")
    _text(item, "duration", placed.source.duration_frames)
    _rate(item, fps)
    _text(item, "start", placed.start)
    _text(item, "end", placed.start + frames.duration_frames)
    _text(item, "in", frames.start_frame)
    _text(item, "out", frames.end_frame)
    return item


def _describe_file(file: ET.Element, source: XmemlFile, fps: int) -> None:
    _text(file, "name", source.name)
    _text(file, "pathurl", "file://localhost" + quote(str(source.path)))
    _rate(file, fps)
    _text(file, "duration", source.duration_frames)
    media = ET.SubElement(file, "media")
    _video_characteristics(ET.SubElement(media, "video"), source, fps)
    audio = ET.SubElement(media, "audio")
    _audio_characteristics(audio, source)
    _text(audio, "channelcount", len(_AUDIO_TRACKS))


def _links(item: ET.Element, clip_index: int) -> None:
    """同じ区間の映像と音声 2 本を結び付ける（Premiere でまとめて動かせるように）。"""
    video = ET.SubElement(item, "link")
    _text(video, "linkclipref", f"v-{clip_index}")
    _text(video, "mediatype", "video")
    _text(video, "trackindex", 1)
    _text(video, "clipindex", clip_index)
    for track_index in _AUDIO_TRACKS:
        audio = ET.SubElement(item, "link")
        _text(audio, "linkclipref", f"a{track_index}-{clip_index}")
        _text(audio, "mediatype", "audio")
        _text(audio, "trackindex", track_index)
        _text(audio, "clipindex", clip_index)
        _text(audio, "groupindex", 1)


def _video_characteristics(parent: ET.Element, source: XmemlFile, fps: int) -> None:
    characteristics = ET.SubElement(parent, "samplecharacteristics")
    _rate(characteristics, fps)
    _text(characteristics, "width", source.width)
    _text(characteristics, "height", source.height)
    _text(characteristics, "pixelaspectratio", "square")


def _audio_characteristics(parent: ET.Element, source: XmemlFile) -> None:
    characteristics = ET.SubElement(parent, "samplecharacteristics")
    _text(characteristics, "depth", _AUDIO_DEPTH)
    _text(characteristics, "samplerate", source.audio_rate)


def _rate(parent: ET.Element, fps: int) -> None:
    rate = ET.SubElement(parent, "rate")
    _text(rate, "timebase", fps)
    _text(rate, "ntsc", "FALSE")


def _text(parent: ET.Element, tag: str, value: str | int) -> None:
    ET.SubElement(parent, tag).text = _NOT_XML_CHARS.sub("_", str(value))
