from pathlib import Path

import pytest

from vidcut.adapters.media.commands import silence_args
from vidcut.adapters.media.silence import parse_silences
from vidcut.domain.intervals import Interval

STDOUT = """frame:12   pts:19200   pts_time:1.2
lavfi.silence_start=1.2
frame:40   pts:64000   pts_time:4
lavfi.silence_end=4.5
lavfi.silence_duration=3.3
frame:90   pts:144000  pts_time:9
lavfi.silence_start=9.0006
"""


class TestParseSilences:
    def test_pairs_starts_and_ends_in_milliseconds(self) -> None:
        assert parse_silences(STDOUT, duration_ms=10_000)[0] == Interval(1_200, 4_500)

    def test_silence_running_to_the_end_is_closed_at_duration(self) -> None:
        assert parse_silences(STDOUT, duration_ms=10_000)[1] == Interval(9_001, 10_000)

    def test_negative_start_is_clamped_to_zero(self) -> None:
        out = "lavfi.silence_start=-0.01\nlavfi.silence_end=0.5\n"
        assert parse_silences(out, duration_ms=1_000) == (Interval(0, 500),)

    def test_empty_or_degenerate_spans_are_dropped(self) -> None:
        out = "lavfi.silence_start=0.9999\n"
        assert parse_silences(out, duration_ms=1_000) == ()
        assert parse_silences("", duration_ms=1_000) == ()

    def test_unreadable_value_is_an_error(self) -> None:
        with pytest.raises(ValueError):
            parse_silences("lavfi.silence_start=abc\n", duration_ms=1_000)


def test_silence_args_print_detections_to_stdout() -> None:
    args = silence_args("ffmpeg", Path("/ws/audio16k.wav"), threshold_db=-40, min_ms=300)
    audio_filter = args[args.index("-af") + 1]
    assert audio_filter == "silencedetect=noise=-40dB:duration=0.300,ametadata=mode=print:file=-"
    assert args[-3:] == ["-f", "null", "-"]
