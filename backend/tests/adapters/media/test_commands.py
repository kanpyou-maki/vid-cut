from collections.abc import Callable
from pathlib import Path

import pytest

from vidcut.adapters.media.commands import (
    MediaSettings,
    audio_args,
    mezzanine_args,
    probe_args,
    proxy_args,
)

SOURCE = Path("/rec/-weird name.mov")
DEST = Path("/ws/out.mp4")


def value_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


class TestProbeArgs:
    def test_requests_json_of_streams_and_format(self) -> None:
        args = probe_args("ffprobe", SOURCE)
        assert args[0] == "ffprobe"
        assert value_after(args, "-of") == "json"
        assert {"-show_streams", "-show_format"} <= set(args)
        assert args[-1] == str(SOURCE)


class TestAudioArgs:
    def test_extracts_16k_mono_pcm(self) -> None:
        args = audio_args("ffmpeg", SOURCE, Path("/ws/audio16k.wav"))
        assert value_after(args, "-ar") == "16000"
        assert value_after(args, "-ac") == "1"
        assert value_after(args, "-c:a") == "pcm_s16le"

    def test_pads_leading_gap_so_wav_starts_at_timeline_zero(self) -> None:
        # 実素材は音声が 51ms 遅れて始まる。wav は時刻を持たないので、先頭を無音で埋めてそろえる
        args = audio_args("ffmpeg", SOURCE, Path("/ws/audio16k.wav"))
        assert "first_pts=0" in value_after(args, "-af")


class TestMezzanineArgs:
    def test_fixes_frame_rate_and_extends_last_frame_to_audio_end(self) -> None:
        args = mezzanine_args("ffmpeg", SOURCE, DEST, duration_ms=30_000, settings=MediaSettings())
        video_filter = value_after(args, "-vf")
        assert video_filter.startswith("fps=60,")
        assert "tpad=stop=-1:stop_mode=clone" in video_filter
        assert value_after(args, "-t") == "30.000"

    def test_encodes_with_videotoolbox_and_copies_audio(self) -> None:
        args = mezzanine_args("ffmpeg", SOURCE, DEST, duration_ms=1_500, settings=MediaSettings())
        assert value_after(args, "-c:v") == "h264_videotoolbox"
        assert value_after(args, "-q:v") == "60"
        assert value_after(args, "-c:a") == "copy"

    def test_frame_rate_is_configurable(self) -> None:
        settings = MediaSettings(mezzanine_fps=30)
        args = mezzanine_args("ffmpeg", SOURCE, DEST, duration_ms=1_000, settings=settings)
        assert value_after(args, "-vf").startswith("fps=30,")

    def test_reports_progress_on_stdout(self) -> None:
        args = mezzanine_args("ffmpeg", SOURCE, DEST, duration_ms=1_000, settings=MediaSettings())
        assert value_after(args, "-progress") == "pipe:1"


class TestProxyArgs:
    def test_scales_long_side_without_upscaling_and_keeps_even_size(self) -> None:
        args = proxy_args("ffmpeg", SOURCE, DEST, duration_ms=1_000, settings=MediaSettings())
        video_filter = value_after(args, "-vf")
        assert video_filter.startswith("fps=30,tpad=stop=-1:stop_mode=clone,scale=")
        assert "min(1280,iw)" in video_filter
        assert "format=yuv420p" in video_filter

    def test_short_keyframe_interval_and_browser_friendly_audio(self) -> None:
        args = proxy_args("ffmpeg", SOURCE, DEST, duration_ms=2_000, settings=MediaSettings())
        assert value_after(args, "-g") == "30"
        assert value_after(args, "-c:a") == "aac"
        assert value_after(args, "-t") == "2.000"


COMMANDS: dict[str, Callable[[], list[str]]] = {
    "audio": lambda: audio_args("ffmpeg", SOURCE, DEST),
    "mezzanine": lambda: mezzanine_args(
        "ffmpeg", SOURCE, DEST, duration_ms=1, settings=MediaSettings()
    ),
    "proxy": lambda: proxy_args("ffmpeg", SOURCE, DEST, duration_ms=1, settings=MediaSettings()),
}


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_ffmpeg_commands_never_prompt_and_pass_paths_as_single_arguments(name: str) -> None:
    args = COMMANDS[name]()
    assert args[0] == "ffmpeg"
    assert "-nostdin" in args
    assert value_after(args, "-i") == str(SOURCE)
    assert args[-1] == str(DEST)


def test_rejects_relative_paths() -> None:
    # 「-」で始まる相対パスがオプションとして解釈されないよう、絶対パスだけを受け付ける
    with pytest.raises(ValueError):
        audio_args("ffmpeg", Path("-y.mov"), DEST)
    with pytest.raises(ValueError):
        probe_args("ffprobe", Path("rec.mov"))


@pytest.mark.parametrize(
    "kwargs",
    [{"mezzanine_fps": 0}, {"proxy_fps": -1}, {"proxy_long_side": 1}, {"mezzanine_quality": 101}],
)
def test_settings_reject_invalid_values(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        MediaSettings(**kwargs)


@pytest.mark.parametrize("name", [*sorted(COMMANDS), "probe"])
def test_inputs_are_restricted_to_local_files(name: str) -> None:
    # 中身がプレイリストのファイルから、ローカルファイル以外を開かせない
    args = probe_args("ffprobe", SOURCE) if name == "probe" else COMMANDS[name]()
    whitelist = args.index("-protocol_whitelist")
    assert args[whitelist + 1] == "file"
    assert whitelist < args.index(str(SOURCE))
