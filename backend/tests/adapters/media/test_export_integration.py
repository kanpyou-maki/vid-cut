"""実物の ffmpeg で、中間素材から切り出した MP4 を確かめる（Design Doc 3-4・6 章、ADR-002）。"""

import shutil
from pathlib import Path

import pytest

from tests.adapters.media.samples import (
    FLASH_TIMES_S,
    FPS,
    beep_starts_s,
    make_vfr_source,
    stream_info,
    white_frame_starts,
)
from vidcut.adapters.media.tool import FfmpegMediaTool
from vidcut.domain.timeline import FrameRange
from vidcut.pipeline.export import mezzanine_frame_count
from vidcut.pipeline.ports import ExternalToolError, MediaClip

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg がない"),
]

AUDIO_OFFSET_S = 0.05
ONE_FRAME_S = 1 / FPS
# 白枠は 30 / 90 / 150 フレーム目。各区間に 1 つずつ入るように切る
CUTS = (FrameRange(0, 60), FrameRange(84, 108), FrameRange(144, 180))
EXPECTED_FLASH_FRAMES = [30, 60 + 6, 60 + 24 + 6]


@pytest.fixture(scope="module")
def tool() -> FfmpegMediaTool:
    return FfmpegMediaTool()


@pytest.fixture(scope="module")
def media_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("export")


def _mezzanine(tool: FfmpegMediaTool, source: Path) -> Path:
    dest = source.with_name(f"{source.stem}-mezzanine.mp4")
    duration_ms = tool.probe(source).duration_ms
    tool.make_mezzanine(source, dest, duration_ms=duration_ms, on_progress=None)
    return dest


@pytest.fixture(scope="module")
def aligned(tool: FfmpegMediaTool, media_dir: Path) -> Path:
    """音声が 0 秒から始まる素材の中間素材。"""
    return _mezzanine(tool, make_vfr_source(media_dir / "aligned.mov"))


@pytest.fixture(scope="module")
def delayed(tool: FfmpegMediaTool, media_dir: Path) -> Path:
    """音声が 50ms 遅れて始まる素材（実素材と同じ）の中間素材。ビープは白枠の 50ms 後に鳴る。"""
    source = make_vfr_source(media_dir / "delayed.mov", audio_offset_s=AUDIO_OFFSET_S)
    return _mezzanine(tool, source)


@pytest.fixture(scope="module")
def exported(tool: FfmpegMediaTool, delayed: Path, media_dir: Path) -> Path:
    dest = media_dir / "exported.mp4"
    clips = [MediaClip(delayed, frames) for frames in CUTS]
    tool.export_mp4(clips, dest, fps=FPS, on_progress=None)
    return dest


class TestMezzanineFrames:
    """Premiere XML に書く中間素材の長さ（フレーム数）が、実際の中間素材と一致すること。"""

    @pytest.mark.parametrize("fixture", ["aligned", "delayed"])
    def test_frame_count_matches_the_recording_duration(
        self, tool: FfmpegMediaTool, fixture: str, request: pytest.FixtureRequest, media_dir: Path
    ) -> None:
        mezzanine: Path = request.getfixturevalue(fixture)
        duration_ms = tool.probe(media_dir / f"{fixture}.mov").duration_ms
        frames = int(stream_info(mezzanine, "v")["nb_frames"])
        assert frames == mezzanine_frame_count(duration_ms, FPS)


class TestExportMp4:
    def test_has_exactly_the_frames_of_the_clips_at_constant_rate(self, exported: Path) -> None:
        video = stream_info(exported, "v")
        assert int(video["nb_frames"]) == sum(frames.duration_frames for frames in CUTS)
        assert video["r_frame_rate"] == video["avg_frame_rate"] == f"{FPS}/1"
        assert video["codec_name"] == "h264"

    def test_audio_is_aac_and_as_long_as_the_video(self, exported: Path) -> None:
        video = stream_info(exported, "v")
        audio = stream_info(exported, "a")
        assert audio["codec_name"] == "aac"
        assert float(audio["start_time"]) == pytest.approx(0.0, abs=ONE_FRAME_S)
        audio_end = float(audio["start_time"]) + float(audio["duration"])
        assert audio_end == pytest.approx(float(video["duration"]), abs=2 * ONE_FRAME_S)

    def test_white_frames_land_where_the_cuts_put_them(self, exported: Path) -> None:
        assert white_frame_starts(exported) == EXPECTED_FLASH_FRAMES

    def test_beeps_keep_their_distance_from_the_white_frames(self, exported: Path) -> None:
        # 元素材と同じく、ビープは白枠の 50ms 後に鳴る。0 秒から始まる最初の区間でも詰まらない
        flashes = [frame / FPS for frame in white_frame_starts(exported)]
        beeps = beep_starts_s(exported)
        assert len(beeps) == len(flashes) == len(FLASH_TIMES_S)
        for flash, beep in zip(flashes, beeps, strict=True):
            assert beep - flash == pytest.approx(AUDIO_OFFSET_S, abs=ONE_FRAME_S)

    def test_clips_from_several_mezzanines_are_joined_in_order(
        self, tool: FfmpegMediaTool, aligned: Path, delayed: Path, tmp_path: Path
    ) -> None:
        dest = tmp_path / "joined.mp4"
        clips = [
            MediaClip(delayed, FrameRange(84, 108)),  # 白枠は 6 フレーム目、ビープはその 50ms 後
            MediaClip(aligned, FrameRange(0, 60)),  # 白枠は 24 + 30 フレーム目、ビープは同時
            MediaClip(delayed, FrameRange(144, 180)),  # 白枠は 84 + 6 フレーム目
        ]
        tool.export_mp4(clips, dest, fps=FPS, on_progress=None)
        assert white_frame_starts(dest) == [6, 54, 90]
        offsets = [
            beep - frame / FPS
            for beep, frame in zip(beep_starts_s(dest), white_frame_starts(dest), strict=True)
        ]
        assert offsets == pytest.approx([AUDIO_OFFSET_S, 0.0, AUDIO_OFFSET_S], abs=ONE_FRAME_S)

    def test_reports_progress_up_to_completion(
        self, tool: FfmpegMediaTool, aligned: Path, tmp_path: Path
    ) -> None:
        reported: list[float] = []
        clips = [MediaClip(aligned, FrameRange(0, 120))]
        tool.export_mp4(clips, tmp_path / "out.mp4", fps=FPS, on_progress=reported.append)
        assert reported[-1] == 1.0
        assert reported == sorted(reported)

    def test_failure_leaves_no_output(self, tool: FfmpegMediaTool, tmp_path: Path) -> None:
        broken = tmp_path / "broken.mp4"
        broken.write_bytes(b"\x00" * 1024)
        dest = tmp_path / "out.mp4"
        with pytest.raises(ExternalToolError):
            tool.export_mp4([MediaClip(broken, FrameRange(0, 60))], dest, fps=FPS, on_progress=None)
        assert list(tmp_path.iterdir()) == [broken]
