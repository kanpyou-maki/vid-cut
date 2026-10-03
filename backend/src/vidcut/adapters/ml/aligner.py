"""Aligner の WhisperX（日本語は wav2vec2）による実装（ADR-003）。"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from vidcut.adapters.ml.audio import load_wav
from vidcut.domain.intervals import Interval
from vidcut.pipeline.ports import AlignedChar


def aligned_chars(segments: Sequence[Mapping[str, Any]]) -> tuple[AlignedChar, ...]:
    """whisperx.align の segments（文ごとに分かれることがある）→ 文字の列。

    時刻の付かない文字は start / end / score のキーが省かれている。
    """
    chars: list[AlignedChar] = []
    for segment in segments:
        for c in segment.get("chars") or []:
            start, end, score = c.get("start"), c.get("end"), c.get("score")
            chars.append(
                AlignedChar(
                    text=str(c["char"]),
                    start_ms=None if start is None else round(float(start) * 1000),
                    end_ms=None if end is None else round(float(end) * 1000),
                    score=None if score is None else float(score),
                )
            )
    return tuple(chars)


class WhisperxAligner:
    def __init__(self, *, language: str = "ja", device: str = "cpu") -> None:
        self._language = language
        self._device = device
        self._model: Any = None
        self._metadata: Any = None
        self.model_id = f"whisperx-default:{language}"

    def align(
        self, audio: Path, segments: Sequence[tuple[Interval, str]]
    ) -> tuple[tuple[AlignedChar, ...], ...]:
        import whisperx

        if self._model is None:
            self._model, self._metadata = whisperx.load_align_model(
                language_code=self._language, device=self._device
            )
        samples = load_wav(audio)
        # 1 チャンクずつ合わせる（まとめて渡すと文単位に分割され、チャンクとの対応が崩れる）
        return tuple(
            self._align_one(whisperx, samples, span, text) if text.strip() else ()
            for span, text in segments
        )

    def _align_one(
        self, whisperx: Any, samples: Any, span: Interval, text: str
    ) -> tuple[AlignedChar, ...]:
        transcript = [{"start": span.start_ms / 1000, "end": span.end_ms / 1000, "text": text}]
        result = whisperx.align(
            transcript,
            self._model,
            self._metadata,
            samples,
            self._device,
            return_char_alignments=True,
        )
        return aligned_chars(result["segments"])
