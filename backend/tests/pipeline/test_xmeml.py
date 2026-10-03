"""Premiere XML（xmeml v4）の生成。形はスパイク S-1 で Premiere に読ませて確かめた（ADR-002）。"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from vidcut.domain.timeline import FrameRange
from vidcut.pipeline.export import ExportClip, ExportPlan
from vidcut.pipeline.xmeml import XmemlFile, build_xmeml

S1_XML = Path(__file__).parent / "data" / "s1_synth_mezzanine.xml"
S1_CUTS = ((0, 150), (258, 402), (576, 744), (948, 1092), (1290, 1476), (1638, 1800))


def plan(*clips: tuple[str, int, int], fps: int = 60) -> ExportPlan:
    return ExportPlan(
        fps=fps, clips=tuple(ExportClip(rid, FrameRange(start, end)) for rid, start, end in clips)
    )


def source(
    name: str = "S05-12.mov",
    path: str = "/ws/recordings/r1/mezzanine.mp4",
    duration_frames: int = 1_800,
    width: int = 1920,
    height: int = 1080,
) -> XmemlFile:
    return XmemlFile(
        name=name,
        path=Path(path),
        duration_frames=duration_frames,
        width=width,
        height=height,
        audio_rate=48_000,
    )


def sequence(xml: str) -> ET.Element:
    found = ET.fromstring(xml).find("sequence")
    assert found is not None
    return found


def texts(parent: ET.Element, path: str) -> list[str | None]:
    return [element.text for element in parent.findall(path)]


def clip_frames(track: ET.Element) -> list[tuple[str, ...]]:
    return [
        tuple(clip.findtext(tag) or "" for tag in ("start", "end", "in", "out"))
        for clip in track.findall("clipitem")
    ]


def test_matches_the_xml_verified_with_premiere_in_spike_s1() -> None:
    xml = build_xmeml(
        "synth_mezzanine",
        plan(*(("r1", start, end) for start, end in S1_CUTS)),
        {"r1": source(name="synth_mezzanine.mp4")},
    )
    expected = S1_XML.read_text(encoding="utf-8")
    assert ET.canonicalize(xml, strip_text=True) == ET.canonicalize(expected, strip_text=True)


def test_starts_with_xml_declaration_and_doctype() -> None:
    xml = build_xmeml("L", plan(("r1", 0, 60)), {"r1": source()})
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml')


class TestSequence:
    def test_duration_is_the_sum_of_clips_at_the_plan_frame_rate(self) -> None:
        seq = sequence(build_xmeml("L", plan(("r1", 0, 60), ("r1", 120, 150)), {"r1": source()}))
        assert seq.findtext("name") == "L"
        assert seq.findtext("duration") == "90"
        assert seq.findtext("rate/timebase") == "60"
        assert seq.findtext("rate/ntsc") == "FALSE"

    def test_has_one_video_track_and_two_audio_tracks(self) -> None:
        seq = sequence(build_xmeml("L", plan(("r1", 0, 60)), {"r1": source()}))
        assert len(seq.findall("media/video/track")) == 1
        assert len(seq.findall("media/audio/track")) == 2
        assert texts(seq, "media/audio/track/outputchannelindex") == ["1", "2"]
        assert texts(seq, "media/audio/track/clipitem/sourcetrack/trackindex") == ["1", "2"]

    def test_format_follows_the_first_mezzanine(self) -> None:
        files = {
            "r1": source(width=3104, height=1964),
            "r2": source(path="/ws/recordings/r2/mezzanine.mp4", width=1920, height=1080),
        }
        seq = sequence(build_xmeml("L", plan(("r1", 0, 60), ("r2", 0, 60)), files))
        characteristics = seq.find("media/video/format/samplecharacteristics")
        assert characteristics is not None
        assert characteristics.findtext("width") == "3104"
        assert characteristics.findtext("height") == "1964"

    def test_other_frame_rates_set_the_timebase_everywhere(self) -> None:
        seq = sequence(build_xmeml("L", plan(("r1", 0, 30), fps=30), {"r1": source()}))
        assert set(texts(seq, ".//timebase")) == {"30"}


class TestClips:
    def test_clips_are_laid_end_to_end_on_every_track(self) -> None:
        seq = sequence(build_xmeml("L", plan(("r1", 0, 150), ("r1", 258, 402)), {"r1": source()}))
        expected = [("0", "150", "0", "150"), ("150", "294", "258", "402")]
        for track in (*seq.findall("media/video/track"), *seq.findall("media/audio/track")):
            assert clip_frames(track) == expected

    def test_video_and_audio_clips_of_one_cut_are_linked(self) -> None:
        seq = sequence(build_xmeml("L", plan(("r1", 0, 150), ("r1", 258, 402)), {"r1": source()}))
        clip_ids = {clip.get("id") for clip in seq.iter("clipitem")}
        assert clip_ids == {"v-1", "v-2", "a1-1", "a1-2", "a2-1", "a2-2"}
        second_audio = seq.find("media/audio/track[2]/clipitem[2]")
        assert second_audio is not None
        assert texts(second_audio, "link/linkclipref") == ["v-2", "a1-2", "a2-2"]
        assert texts(second_audio, "link/clipindex") == ["2", "2", "2"]
        assert texts(second_audio, "link/trackindex") == ["1", "1", "2"]

    def test_each_mezzanine_is_described_once_and_referenced_by_id(self) -> None:
        files = {
            "r1": source(name="a.mov", path="/ws/recordings/r1/mezzanine.mp4"),
            "r2": source(name="b.mov", path="/ws/recordings/r2/mezzanine.mp4", duration_frames=900),
        }
        cuts = plan(("r1", 0, 60), ("r1", 90, 120), ("r2", 30, 90))
        seq = sequence(build_xmeml("L", cuts, files))
        described = [f for f in seq.iter("file") if f.find("pathurl") is not None]
        assert [f.get("id") for f in described] == ["file-1", "file-2"]
        assert texts(seq, "media/video/track/clipitem/file/pathurl") == [
            "file://localhost/ws/recordings/r1/mezzanine.mp4",
            "file://localhost/ws/recordings/r2/mezzanine.mp4",
        ]
        video = seq.find("media/video/track")
        assert video is not None
        assert [c.find("file").get("id") for c in video.findall("clipitem")] == [  # type: ignore[union-attr]
            "file-1",
            "file-1",
            "file-2",
        ]
        assert texts(video, "clipitem/name") == ["a.mov", "a.mov", "b.mov"]
        # クリップの duration は参照する中間素材の長さ
        assert texts(video, "clipitem/duration") == ["1800", "1800", "900"]
        assert clip_frames(video)[2] == ("90", "150", "30", "90")

    def test_recordings_out_of_time_order_keep_the_plan_order(self) -> None:
        files = {"r1": source(), "r2": source(path="/ws/recordings/r2/mezzanine.mp4")}
        seq = sequence(build_xmeml("L", plan(("r2", 100, 160), ("r1", 0, 60)), files))
        assert texts(seq, "media/video/track/clipitem/file/pathurl") == [
            "file://localhost/ws/recordings/r2/mezzanine.mp4",
            "file://localhost/ws/recordings/r1/mezzanine.mp4",
        ]


class TestEscaping:
    def test_path_is_percent_encoded(self) -> None:
        files = {"r1": source(path="/Users/福田/Vid Cut/a&b#1/mezzanine.mp4")}
        seq = sequence(build_xmeml("L", plan(("r1", 0, 60)), files))
        assert seq.findtext(".//pathurl") == (
            "file://localhost/Users/%E7%A6%8F%E7%94%B0/Vid%20Cut/a%26b%231/mezzanine.mp4"
        )

    def test_names_with_markup_characters_survive_a_round_trip(self) -> None:
        title = '講座 <1> & "2"'
        files = {"r1": source(name="a<b>&c.mov")}
        seq = sequence(build_xmeml(title, plan(("r1", 0, 60)), files))
        assert seq.findtext("name") == title
        assert seq.findtext("media/video/track/clipitem/name") == "a<b>&c.mov"

    def test_characters_that_xml_cannot_hold_are_replaced(self) -> None:
        # 制御文字はエスケープしても XML 1.0 に書けず、Premiere が読み込めなくなる
        files = {"r1": source(name="a\x00b\x1fc.mov")}
        xml = build_xmeml("題\x0b名\ttab", plan(("r1", 0, 60)), files)
        seq = sequence(xml)
        assert seq.findtext("name") == "題_名\ttab"
        assert seq.findtext("media/video/track/clipitem/name") == "a_b_c.mov"


class TestInvalidInput:
    def test_empty_plan_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="残す区間"):
            build_xmeml("L", plan(), {"r1": source()})

    def test_clip_without_a_mezzanine_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="r2"):
            build_xmeml("L", plan(("r2", 0, 60)), {"r1": source()})

    def test_clip_beyond_the_end_of_the_mezzanine_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="長さ"):
            build_xmeml("L", plan(("r1", 0, 61)), {"r1": source(duration_frames=60)})

    def test_relative_path_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="絶対パス"):
            build_xmeml("L", plan(("r1", 0, 60)), {"r1": source(path="mezzanine.mp4")})
