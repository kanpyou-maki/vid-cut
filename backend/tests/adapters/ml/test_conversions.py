"""ML ライブラリの出力 → ports の型への変換（モデルは使わない）。"""

import array
import wave
from pathlib import Path

import numpy as np
import pytest

from vidcut.adapters.ml.aligner import aligned_chars
from vidcut.adapters.ml.audio import load_wav, slice_ms
from vidcut.adapters.ml.transcriber import chunk_transcript
from vidcut.adapters.ml.vad import speech_spans
from vidcut.domain.intervals import Interval
from vidcut.pipeline.ports import AlignedChar, ChunkTranscript


def write_wav(path: Path, samples: list[int], rate: int = 16_000) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(array.array("h", samples).tobytes())
    return path


class TestAudio:
    def test_load_wav_as_float32_in_unit_range(self, tmp_path: Path) -> None:
        audio = load_wav(write_wav(tmp_path / "a.wav", [0, 16384, -32768]))
        assert audio.dtype == np.float32
        assert audio.tolist() == [0.0, 0.5, -1.0]

    def test_load_wav_rejects_other_formats(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            load_wav(write_wav(tmp_path / "a.wav", [0, 1], rate=48_000))

    def test_slice_by_milliseconds(self) -> None:
        audio = np.arange(16_000, dtype=np.float32)
        assert slice_ms(audio, Interval(500, 501)).tolist() == list(range(8_000, 8_016))


class TestSpeechSpans:
    def test_sample_positions_to_milliseconds(self) -> None:
        stamps = [{"start": 16_000, "end": 24_000}, {"start": 32_000, "end": 32_008}]
        assert speech_spans(stamps, rate=16_000) == (Interval(1_000, 1_500), Interval(2_000, 2_001))


class TestChunkTranscript:
    def test_joins_segments_without_spaces(self) -> None:
        result = {
            "text": "ignored",
            "segments": [
                {"text": " 前のレクチャーでは", "avg_logprob": -0.2, "start": 0.0, "end": 1.0},
                {"text": "扱いました。 ", "avg_logprob": -0.5, "start": 1.0, "end": 4.0},
            ],
        }
        transcript = chunk_transcript(result)
        assert transcript.text == "前のレクチャーでは扱いました。"
        # 長さで重み付けした平均: (-0.2×1 + -0.5×3) / 4
        assert transcript.avg_logprob == pytest.approx(-0.425)

    def test_no_segments_is_empty_text(self) -> None:
        assert chunk_transcript({"text": "", "segments": []}) == ChunkTranscript("", 0.0)

    def test_zero_length_segments_use_plain_mean(self) -> None:
        result = {"segments": [{"text": "あ", "avg_logprob": -1.0, "start": 1.0, "end": 1.0}]}
        assert chunk_transcript(result).avg_logprob == -1.0


class TestAlignedChars:
    def test_collects_characters_of_all_sentences_in_milliseconds(self) -> None:
        segments = [
            {"chars": [{"char": "こ", "start": 1.0, "end": 1.1, "score": 0.9}]},
            {"chars": [{"char": "、"}, {"char": "れ", "start": 1.25, "end": 1.4, "score": 0.8}]},
        ]
        assert aligned_chars(segments) == (
            AlignedChar("こ", 1_000, 1_100, 0.9),
            AlignedChar("、", None, None, None),
            AlignedChar("れ", 1_250, 1_400, 0.8),
        )

    def test_missing_chars_list_is_empty(self) -> None:
        assert aligned_chars([{"text": "x"}]) == ()
