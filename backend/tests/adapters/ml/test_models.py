"""実物のモデルを使うテスト（既定では除外。`uv run pytest -m ml` で実行）。検証素材の冒頭を使う。"""

from pathlib import Path

import pytest

from vidcut.adapters.media.tool import FfmpegMediaTool
from vidcut.adapters.ml.aligner import WhisperxAligner
from vidcut.adapters.ml.transcriber import MlxWhisperTranscriber
from vidcut.adapters.ml.vad import SileroVad
from vidcut.domain.intervals import Interval

SAMPLE = Path.home() / "Desktop" / "s05-12sample.mov"
# 正解データ（docs/references/prototype/sample-chunks.json）の最初のチャンク
FIRST_CHUNK = Interval(8_197, 11_288)

pytestmark = [
    pytest.mark.ml,
    pytest.mark.skipif(not SAMPLE.exists(), reason="検証素材がない"),
]


@pytest.fixture(scope="module")
def audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dest = tmp_path_factory.mktemp("ml") / "audio16k.wav"
    FfmpegMediaTool().extract_audio(SAMPLE, dest)
    return dest


def test_vad_finds_the_first_utterance(audio: Path) -> None:
    speech = SileroVad().detect_speech(audio)
    first = speech[0]
    assert abs(first.start_ms - FIRST_CHUNK.start_ms) < 300


def test_transcribes_and_aligns_the_first_chunk(audio: Path) -> None:
    (transcript,) = MlxWhisperTranscriber().transcribe(
        audio, [FIRST_CHUNK], hint="えー、それでは説明していきます。", on_progress=None
    )
    assert "レクチャー" in transcript.text
    assert transcript.avg_logprob > -0.5

    (chars,) = WhisperxAligner().align(audio, [(FIRST_CHUNK, transcript.text)])
    starts = [c.start_ms for c in chars if c.start_ms is not None]
    assert len(starts) >= len(transcript.text) * 0.9
    assert all(FIRST_CHUNK.start_ms - 50 <= ms <= FIRST_CHUNK.end_ms for ms in starts)
