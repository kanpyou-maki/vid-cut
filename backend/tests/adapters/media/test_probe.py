from datetime import UTC, datetime
from typing import Any

import pytest

from vidcut.adapters.media.probe import parse_probe
from vidcut.pipeline.ports import UnsupportedMediaError


def video_stream(**overrides: Any) -> dict[str, Any]:
    stream = {
        "codec_type": "video",
        "width": 3104,
        "height": 1964,
        "r_frame_rate": "60/1",
        "avg_frame_rate": "354600/110687",
        "start_time": "0.000000",
        "duration": "368.940000",
    }
    return {**stream, **overrides}


def audio_stream(**overrides: Any) -> dict[str, Any]:
    stream = {
        "codec_type": "audio",
        "sample_rate": "48000",
        "start_time": "0.051250",
        "duration": "368.925917",
    }
    return {**stream, **overrides}


def ffprobe_output(
    streams: list[dict[str, Any]] | None = None, tags: dict[str, str] | None = None
) -> dict[str, Any]:
    return {
        "streams": [video_stream(), audio_stream()] if streams is None else streams,
        "format": {"duration": "368.977167", "tags": tags or {}},
    }


class TestParseProbe:
    def test_reads_media_info_of_screen_recording(self) -> None:
        result = parse_probe(ffprobe_output())
        assert (result.media.width, result.media.height) == (3104, 1964)
        assert result.media.audio_rate == 48000
        assert result.media.avg_fps == pytest.approx(3.2037, abs=1e-3)

    def test_variable_frame_rate_when_average_differs_from_nominal(self) -> None:
        assert parse_probe(ffprobe_output()).media.is_vfr

    def test_constant_frame_rate_when_average_matches_nominal(self) -> None:
        streams = [video_stream(r_frame_rate="30/1", avg_frame_rate="30/1"), audio_stream()]
        result = parse_probe(ffprobe_output(streams))
        assert not result.media.is_vfr
        assert result.media.avg_fps == 30.0

    def test_falls_back_to_nominal_rate_when_average_is_unknown(self) -> None:
        streams = [video_stream(r_frame_rate="25/1", avg_frame_rate="0/0"), audio_stream()]
        result = parse_probe(ffprobe_output(streams))
        assert result.media.avg_fps == 25.0
        assert not result.media.is_vfr

    def test_duration_is_end_of_audio_including_its_start_offset(self) -> None:
        # 実素材では音声が 51ms 遅れて始まる。タイムラインの長さは音声の終わり
        assert parse_probe(ffprobe_output()).duration_ms == 368_977

    def test_audio_duration_falls_back_to_format_duration(self) -> None:
        streams = [video_stream(), audio_stream(duration=None, start_time=None)]
        assert parse_probe(ffprobe_output(streams)).duration_ms == 368_977

    def test_reads_creation_time_as_recorded_at(self) -> None:
        result = parse_probe(ffprobe_output(tags={"creation_time": "2026-09-10T14:26:00.000000Z"}))
        assert result.recorded_at == datetime(2026, 9, 10, 14, 26, tzinfo=UTC)

    @pytest.mark.parametrize("tags", [{}, {"creation_time": "not a date"}])
    def test_recorded_at_is_none_when_missing_or_invalid(self, tags: dict[str, str]) -> None:
        assert parse_probe(ffprobe_output(tags=tags)).recorded_at is None

    def test_ignores_cover_art_streams(self) -> None:
        cover = video_stream(width=600, height=600, disposition={"attached_pic": 1})
        result = parse_probe(ffprobe_output([cover, video_stream(), audio_stream()]))
        assert result.media.width == 3104

    def test_rejects_file_without_audio(self) -> None:
        with pytest.raises(UnsupportedMediaError, match="音声"):
            parse_probe(ffprobe_output([video_stream()]))

    def test_rejects_file_without_video(self) -> None:
        with pytest.raises(UnsupportedMediaError, match="映像"):
            parse_probe(ffprobe_output([audio_stream()]))

    @pytest.mark.parametrize(
        "broken",
        [
            {"streams": "x"},
            {"format": {}},
            ffprobe_output([video_stream(width="abc"), audio_stream()]),
            ffprobe_output(
                [video_stream(r_frame_rate="0/0", avg_frame_rate="0/0"), audio_stream()]
            ),
            ffprobe_output([video_stream(), audio_stream(sample_rate=None)]),
            {
                "streams": [video_stream(), audio_stream(duration=None)],
                "format": {"duration": "N/A"},
            },
        ],
    )
    def test_rejects_unreadable_metadata(self, broken: dict[str, Any]) -> None:
        with pytest.raises(UnsupportedMediaError):
            parse_probe(broken)
