import array
import wave
from pathlib import Path

import pytest

from vidcut.adapters.media.waveform import compute_peaks, wav_duration_ms


def write_wav(
    path: Path, samples: list[int], *, rate: int = 16_000, channels: int = 1, width: int = 2
) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        if width == 2:
            wav.writeframes(array.array("h", samples).tobytes())
        else:
            wav.writeframes(bytes(len(samples) * width))
    return path


class TestComputePeaks:
    def test_one_value_per_bucket_normalized_to_unit_range(self, tmp_path: Path) -> None:
        # 100 個/秒 → 160 サンプルごと。2 番目のバケットだけに音がある
        samples = [0] * 160 + [16384, -32768] + [0] * 158 + [0] * 160
        peaks = compute_peaks(write_wav(tmp_path / "a.wav", samples), per_second=100)
        assert peaks.per_second == 100
        assert peaks.values == (0.0, 1.0, 0.0)

    def test_last_partial_bucket_is_included(self, tmp_path: Path) -> None:
        samples = [0] * 160 + [8192] * 10
        peaks = compute_peaks(write_wav(tmp_path / "a.wav", samples), per_second=100)
        assert peaks.values == (0.0, 0.25)

    def test_values_are_rounded_for_compact_json(self, tmp_path: Path) -> None:
        peaks = compute_peaks(write_wav(tmp_path / "a.wav", [12345] * 160), per_second=100)
        assert peaks.values == (0.377,)

    def test_reads_long_audio_in_pieces(self, tmp_path: Path) -> None:
        samples = [1000] * (16_000 * 3)
        peaks = compute_peaks(write_wav(tmp_path / "a.wav", samples), per_second=50)
        assert len(peaks.values) == 150

    def test_empty_audio_has_no_peaks(self, tmp_path: Path) -> None:
        assert compute_peaks(write_wav(tmp_path / "a.wav", []), per_second=100).values == ()

    @pytest.mark.parametrize("per_second", [0, -1, 3])
    def test_rejects_rate_that_does_not_divide_sample_rate(
        self, tmp_path: Path, per_second: int
    ) -> None:
        with pytest.raises(ValueError):
            compute_peaks(write_wav(tmp_path / "a.wav", [0] * 10), per_second=per_second)

    def test_rejects_stereo_or_non_16bit(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            compute_peaks(write_wav(tmp_path / "s.wav", [0] * 4, channels=2), per_second=100)
        with pytest.raises(ValueError):
            compute_peaks(write_wav(tmp_path / "b.wav", [0] * 4, width=1), per_second=100)


def test_wav_duration_in_milliseconds(tmp_path: Path) -> None:
    assert wav_duration_ms(write_wav(tmp_path / "a.wav", [0] * 24_000)) == 1_500
