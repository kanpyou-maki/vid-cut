from pathlib import Path

import pytest

from vidcut.adapters.media.commands import MediaSettings, export_args, export_decoded_ms
from vidcut.domain.timeline import FrameRange
from vidcut.pipeline.ports import MediaClip

FIRST = Path("/ws/recordings/r1/mezzanine.mp4")
SECOND = Path("/ws/recordings/r2/mezzanine.mp4")
DEST = Path("/ws/exports/L/L.mp4")


def clip(source: Path, start: int, end: int) -> MediaClip:
    return MediaClip(source, FrameRange(start, end))


def value_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def graph(clips: list[MediaClip], fps: int = 60) -> list[str]:
    args = export_args("ffmpeg", clips, DEST, fps=fps, settings=MediaSettings())
    return value_after(args, "-filter_complex").split(";")


class TestFilterGraph:
    def test_video_is_trimmed_by_frame_numbers(self) -> None:
        # 時刻の小数で切ると、境界のフレームが丸めの誤差で落ちることがある
        chains = graph([clip(FIRST, 0, 150), clip(FIRST, 258, 402)])
        assert "[s0v]trim=start_frame=0:end_frame=150,setpts=PTS-STARTPTS[c0v]" in chains
        assert "[s1v]trim=start_frame=258:end_frame=402,setpts=PTS-STARTPTS[c1v]" in chains

    def test_audio_is_trimmed_at_the_same_frame_boundaries(self) -> None:
        chains = graph([clip(FIRST, 0, 150), clip(FIRST, 259, 402)])
        assert "[s0a]atrim=start=0.000000:end=2.500000,asetpts=PTS-STARTPTS[c0a]" in chains
        assert "[s1a]atrim=start=4.316667:end=6.700000,asetpts=PTS-STARTPTS[c1a]" in chains

    def test_audio_times_follow_the_frame_rate(self) -> None:
        chains = graph([clip(FIRST, 30, 60)], fps=30)
        assert "[s0a]atrim=start=1.000000:end=2.000000,asetpts=PTS-STARTPTS[c0a]" in chains

    def test_each_mezzanine_is_split_once_for_its_clips(self) -> None:
        chains = graph([clip(FIRST, 0, 60), clip(SECOND, 0, 60), clip(FIRST, 90, 120)])
        assert "[0:v:0]split=2[s0v][s2v]" in chains
        assert "[1:v:0]split=1[s1v]" in chains

    def test_leading_audio_gap_is_filled_before_cutting(self) -> None:
        # 中間素材の音声は元素材と同じく遅れて始まる。埋めておかないと、
        # 0 秒から始まる区間の音声が前に詰まってずれる
        chains = graph([clip(FIRST, 0, 60), clip(FIRST, 90, 120)])
        assert "[0:a:0]aresample=async=1:first_pts=0,asplit=2[s0a][s1a]" in chains

    def test_clips_are_concatenated_in_the_given_order(self) -> None:
        chains = graph([clip(SECOND, 0, 60), clip(FIRST, 0, 60), clip(SECOND, 90, 120)])
        assert "[c0v][c0a][c1v][c1a][c2v][c2a]concat=n=3:v=1:a=1[joinedv][outa]" in chains

    def test_joined_video_is_put_back_on_the_constant_frame_rate_grid(self) -> None:
        # concat の出力はマイクロ秒単位の時刻になり、そのままでは固定フレームレートと認識されない
        assert graph([clip(FIRST, 0, 60)], fps=30)[-1] == "[joinedv]fps=30[outv]"


class TestExportArgs:
    def test_each_mezzanine_is_one_input_in_order_of_first_use(self) -> None:
        clips = [clip(SECOND, 0, 60), clip(FIRST, 0, 60), clip(SECOND, 90, 120)]
        args = export_args("ffmpeg", clips, DEST, fps=60, settings=MediaSettings())
        inputs = [args[i + 1] for i, arg in enumerate(args) if arg == "-i"]
        assert inputs == [str(SECOND), str(FIRST)]

    def test_every_input_is_restricted_to_local_files(self) -> None:
        clips = [clip(FIRST, 0, 60), clip(SECOND, 0, 60)]
        args = export_args("ffmpeg", clips, DEST, fps=60, settings=MediaSettings())
        for index in (i for i, arg in enumerate(args) if arg == "-i"):
            assert args[index - 2 : index] == ["-protocol_whitelist", "file"]

    def test_encodes_with_videotoolbox_and_aac(self) -> None:
        args = export_args("ffmpeg", [clip(FIRST, 0, 60)], DEST, fps=60, settings=MediaSettings())
        assert value_after(args, "-c:v") == "h264_videotoolbox"
        assert value_after(args, "-q:v") == "60"
        assert value_after(args, "-c:a") == "aac"
        assert value_after(args, "-b:a") == "192k"
        assert [args[i + 1] for i, arg in enumerate(args) if arg == "-map"] == ["[outv]", "[outa]"]

    def test_quality_and_bitrate_are_configurable(self) -> None:
        settings = MediaSettings(export_quality=45, export_audio_bitrate="128k")
        args = export_args("ffmpeg", [clip(FIRST, 0, 60)], DEST, fps=60, settings=settings)
        assert value_after(args, "-q:v") == "45"
        assert value_after(args, "-b:a") == "128k"

    def test_never_prompts_reports_progress_and_writes_to_dest(self) -> None:
        args = export_args("ffmpeg", [clip(FIRST, 0, 60)], DEST, fps=60, settings=MediaSettings())
        assert args[0] == "ffmpeg"
        assert "-nostdin" in args
        assert value_after(args, "-progress") == "pipe:1"
        assert args[-1] == str(DEST)

    def test_rejects_no_clips(self) -> None:
        with pytest.raises(ValueError, match="残す区間"):
            export_args("ffmpeg", [], DEST, fps=60, settings=MediaSettings())

    def test_rejects_relative_paths(self) -> None:
        with pytest.raises(ValueError):
            export_args(
                "ffmpeg", [clip(Path("m.mp4"), 0, 60)], DEST, fps=60, settings=MediaSettings()
            )

    def test_rejects_non_positive_frame_rate(self) -> None:
        with pytest.raises(ValueError):
            export_args("ffmpeg", [clip(FIRST, 0, 60)], DEST, fps=0, settings=MediaSettings())


def test_export_quality_must_be_in_range() -> None:
    with pytest.raises(ValueError):
        MediaSettings(export_quality=0)


def test_decoded_length_is_up_to_the_last_frame_used_of_each_mezzanine() -> None:
    # ffmpeg は各中間素材を、最後に使うフレームまで読む。タイムアウトの見積もりに使う
    clips = [clip(FIRST, 0, 60), clip(SECOND, 0, 120), clip(FIRST, 540, 600)]
    assert export_decoded_ms(clips, fps=60) == 10_000 + 2_000
