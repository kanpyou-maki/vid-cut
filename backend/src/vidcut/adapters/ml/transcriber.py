"""Transcriber の mlx-whisper による実装（ADR-003）。"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from vidcut.adapters.ml.audio import load_wav, slice_ms
from vidcut.domain.intervals import Interval
from vidcut.pipeline.ports import ChunkTranscript, ProgressCallback

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def chunk_transcript(result: Mapping[str, Any]) -> ChunkTranscript:
    """mlx_whisper.transcribe の結果 → 1 チャンクの文字起こし。

    avg_logprob はセグメントの長さで重み付けした平均。日本語なのでセグメントは空白なしでつなぐ。
    """
    segments = result.get("segments") or []
    if not segments:
        return ChunkTranscript("", 0.0)
    text = "".join(str(s["text"]).strip() for s in segments)
    weights = [max(float(s["end"]) - float(s["start"]), 0.0) for s in segments]
    logprobs = [float(s["avg_logprob"]) for s in segments]
    total = sum(weights)
    if total == 0:
        return ChunkTranscript(text, sum(logprobs) / len(logprobs))
    return ChunkTranscript(
        text, sum(w * lp for w, lp in zip(weights, logprobs, strict=True)) / total
    )


class MlxWhisperTranscriber:
    def __init__(self, *, model: str = DEFAULT_MODEL, language: str = "ja") -> None:
        self._model = model
        self._language = language
        self.model_id = f"{model}:{language}"

    def transcribe(
        self,
        audio: Path,
        spans: Sequence[Interval],
        *,
        hint: str,
        on_progress: ProgressCallback | None,
    ) -> tuple[ChunkTranscript, ...]:
        import mlx_whisper

        samples = load_wav(audio)
        transcripts = []
        for index, span in enumerate(spans):
            result = mlx_whisper.transcribe(
                slice_ms(samples, span),
                path_or_hf_repo=self._model,
                language=self._language,
                initial_prompt=hint,
                # 時刻は位置合わせで取る。単語の時刻を求めると処理時間がほぼ倍になる（S-2）
                word_timestamps=False,
                condition_on_previous_text=False,
                verbose=None,
            )
            transcripts.append(chunk_transcript(result))
            if on_progress:
                on_progress((index + 1) / len(spans))
        return tuple(transcripts)
