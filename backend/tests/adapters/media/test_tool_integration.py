"""実物の ffmpeg を使う integration テスト。可変フレームレートの回帰テストを含む（ADR-002）。"""

import shutil
import wave
from pathlib import Path

import pytest

from tests.adapters.media.samples import (
    DURATION_S,
    FLASH_TIMES_S,
    FPS,
    beep_starts_s,
    make_vfr_source,
    stream_info,
    white_frame_starts,
)
from vidcut.adapters.media.tool import FfmpegMediaTool
from vidcut.pipeline.ports import ExternalToolError, UnsupportedMediaError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg がない"),
]

AUDIO_OFFSET_S = 0.05
ONE_FRAME_S = 1 / FPS


@pytest.fixture(scope="module")
def media_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="module")
def vfr_source(media_dir: Path) -> Path:
    return make_vfr_source(media_dir / "vfr.mov")


@pytest.fixture(scope="module")
def offset_source(media_dir: Path) -> Path:
    return make_vfr_source(media_dir / "offset.mov", audio_offset_s=AUDIO_OFFSET_S)


@pytest.fixture(scope="module")
def tool() -> FfmpegMediaTool:
    return FfmpegMediaTool()


@pytest.fixture(scope="module")
def mezzanine(tool: FfmpegMediaTool, vfr_source: Path, media_dir: Path) -> Path:
    dest = media_dir / "mezzanine.mp4"
    duration_ms = tool.probe(vfr_source).duration_ms
    tool.make_mezzanine(vfr_source, dest, duration_ms=duration_ms, on_progress=None)
    return dest


class TestProbe:
    def test_detects_variable_frame_rate_screen_recording(
        self, tool: FfmpegMediaTool, vfr_source: Path
    ) -> None:
        result = tool.probe(vfr_source)
        assert result.media.is_vfr
        assert (result.media.width, result.media.height) == (160, 120)
        assert result.media.audio_rate == 48_000

    def test_duration_is_audio_end_even_when_video_ends_earlier(
        self, tool: FfmpegMediaTool, offset_source: Path
    ) -> None:
        video_end = float(stream_info(offset_source, "v")["duration"])
        result = tool.probe(offset_source)
        assert video_end < DURATION_S - 1
        assert result.duration_ms == pytest.approx((DURATION_S + AUDIO_OFFSET_S) * 1000, abs=30)

    def test_constant_frame_rate_output_is_not_vfr(
        self, tool: FfmpegMediaTool, mezzanine: Path
    ) -> None:
        result = tool.probe(mezzanine)
        assert not result.media.is_vfr
        assert result.media.avg_fps == pytest.approx(FPS)

    def test_non_media_file_is_rejected(self, tool: FfmpegMediaTool, tmp_path: Path) -> None:
        text = tmp_path / "notes.mov"
        text.write_text("not a video")
        with pytest.raises((ExternalToolError, UnsupportedMediaError)):
            tool.probe(text)


class TestMezzanineRegression:
    """可変フレームレートの素材を中間素材にしても、映像と音声がずれないこと（ADR-002、S-1）。"""

    def test_video_is_extended_to_the_end_of_audio(self, mezzanine: Path) -> None:
        video = stream_info(mezzanine, "v")
        audio = stream_info(mezzanine, "a")
        audio_end = float(audio["start_time"]) + float(audio["duration"])
        assert float(video["duration"]) == pytest.approx(audio_end, abs=ONE_FRAME_S)
        assert int(video["nb_frames"]) == pytest.approx(audio_end * FPS, abs=1)

    def test_frame_rate_is_constant(self, mezzanine: Path) -> None:
        video = stream_info(mezzanine, "v")
        assert video["r_frame_rate"] == video["avg_frame_rate"] == f"{FPS}/1"

    def test_white_frames_land_on_the_expected_frame_numbers(self, mezzanine: Path) -> None:
        assert white_frame_starts(mezzanine) == [round(t * FPS) for t in FLASH_TIMES_S]

    def test_white_frames_and_beeps_are_within_one_frame(self, mezzanine: Path) -> None:
        flashes = [frame / FPS for frame in white_frame_starts(mezzanine)]
        beeps = beep_starts_s(mezzanine)
        assert len(beeps) == len(flashes) == len(FLASH_TIMES_S)
        for flash, beep in zip(flashes, beeps, strict=True):
            assert abs(flash - beep) <= ONE_FRAME_S

    def test_reports_progress_up_to_completion(
        self, tool: FfmpegMediaTool, vfr_source: Path, tmp_path: Path
    ) -> None:
        reported: list[float] = []
        dest = tmp_path / "m.mp4"
        tool.make_mezzanine(vfr_source, dest, duration_ms=4_000, on_progress=reported.append)
        assert reported[-1] == 1.0
        assert reported == sorted(reported)


class TestExtractAudio:
    def test_wav_is_16k_mono_and_aligned_to_timeline(
        self, tool: FfmpegMediaTool, offset_source: Path, tmp_path: Path
    ) -> None:
        dest = tmp_path / "audio16k.wav"
        tool.extract_audio(offset_source, dest)
        with wave.open(str(dest)) as wav:
            assert (wav.getframerate(), wav.getnchannels()) == (16_000, 1)
        # 音声の遅れ（50ms）が wav の先頭の無音として残り、ビープがタイムラインの時刻に出る
        expected = [t + AUDIO_OFFSET_S for t in FLASH_TIMES_S]
        assert beep_starts_s(dest, rate=16_000) == pytest.approx(expected, abs=0.01)

    def test_peaks_follow_the_beeps(
        self, tool: FfmpegMediaTool, vfr_source: Path, tmp_path: Path
    ) -> None:
        dest = tmp_path / "audio16k.wav"
        tool.extract_audio(vfr_source, dest)
        peaks = tool.compute_peaks(dest, per_second=100)
        assert peaks.values[55] > 0.1  # 0.55 秒はビープの最中
        assert peaks.values[80] < 0.01  # 0.80 秒は無音
        assert len(peaks.values) == pytest.approx(DURATION_S * 100, abs=3)


class TestDetectSilences:
    def test_gaps_between_beeps_are_silences(
        self, tool: FfmpegMediaTool, vfr_source: Path, tmp_path: Path
    ) -> None:
        audio = tmp_path / "audio16k.wav"
        tool.extract_audio(vfr_source, audio)
        silences = tool.detect_silences(audio, threshold_db=-40, min_ms=300)
        # ビープは 0.5〜0.6 / 1.5〜1.6 / 2.5〜2.6 秒。その間と前後が無音
        expected = [0, 500, 600, 1_500, 1_600, 2_500, 2_600, 4_000]
        edges = [ms for span in silences for ms in (span.start_ms, span.end_ms)]
        assert edges == pytest.approx(expected, abs=15)


class TestProxy:
    def test_light_constant_rate_video_covering_whole_audio(
        self, tool: FfmpegMediaTool, vfr_source: Path, tmp_path: Path
    ) -> None:
        dest = tmp_path / "proxy.mp4"
        tool.make_proxy(vfr_source, dest, duration_ms=4_000, on_progress=None)
        video = stream_info(dest, "v")
        assert (int(video["width"]), int(video["height"])) == (160, 120)  # 拡大はしない
        assert video["avg_frame_rate"] == "30/1"
        assert float(video["duration"]) == pytest.approx(DURATION_S, abs=1 / 30)
        assert stream_info(dest, "a")["codec_name"] == "aac"


def test_failed_conversion_leaves_no_output(tool: FfmpegMediaTool, tmp_path: Path) -> None:
    broken = tmp_path / "broken.mov"
    broken.write_bytes(b"\x00" * 1024)
    dest = tmp_path / "mezzanine.mp4"
    with pytest.raises(ExternalToolError):
        tool.make_mezzanine(broken, dest, duration_ms=1_000, on_progress=None)
    assert list(tmp_path.iterdir()) == [broken]
