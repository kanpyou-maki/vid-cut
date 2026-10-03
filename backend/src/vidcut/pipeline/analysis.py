"""録画ファイルの解析（ジョブ analyze_recording。Design Doc 3-2 の段 3〜8）。"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, Recording, Silence, SpeechChunk, Token
from vidcut.pipeline import serialization as ser
from vidcut.pipeline.analysis_result import Analysis, load_analysis, save_analysis
from vidcut.pipeline.fillers import detect_fillers
from vidcut.pipeline.ports import (
    Aligner,
    ArtifactStore,
    ChunkTranscript,
    MediaTool,
    ProgressCallback,
    ProgressReporter,
    Transcriber,
    VoiceActivityDetector,
)
from vidcut.pipeline.review import review_marks
from vidcut.pipeline.silence import find_silences, split_chunks
from vidcut.pipeline.stages import StageCache, require_source, stage_key
from vidcut.pipeline.transcript import build_tokens

__all__ = ["Analysis", "AnalysisSettings", "AnalysisTools", "analyze_recording", "load_analysis"]

_logger = logging.getLogger(__name__)

AUDIO_FILE = "audio16k.wav"
PROXY_FILE = "proxy.mp4"
PEAKS_FILE = "peaks.json"
# ffmpeg の引数やモデルを変えたら上げる（キーが変わり、その段から作り直す）
_FORMAT_VERSION = 1

# 段ごとの進捗の重み（検証素材の実測: proxy 38 秒、文字起こし 99 秒、位置合わせ 21 秒）
_WEIGHTS = {
    "audio": 0.02,
    "silence": 0.05,
    "proxy": 0.18,
    "transcribe": 0.5,
    "align": 0.2,
    "finish": 0.05,
}


@dataclass(frozen=True)
class AnalysisSettings:
    silence_threshold_db: float = -40.0
    silence_min_ms: int = 300
    min_chunk_ms: int = 100
    peaks_per_second: int = 100
    # Whisper はフィラーを省きがちなので、ヒント文にフィラーを含める（ADR-003）
    transcribe_hint: str = "えー、あのー、えーと、それでは説明していきます。"
    low_confidence_logprob: float = -0.5
    min_unrecognized_ms: int = 300
    filler_min_gap_ms: int = 100


@dataclass(frozen=True)
class AnalysisTools:
    media: MediaTool
    vad: VoiceActivityDetector
    transcriber: Transcriber
    aligner: Aligner
    store: ArtifactStore


@dataclass(frozen=True)
class _Segmentation:
    silences: tuple[Interval, ...]
    speech: tuple[Interval, ...]
    chunks: tuple[SpeechChunk, ...]


def analyze_recording(
    recording: Recording,
    tools: AnalysisTools,
    settings: AnalysisSettings,
    report: ProgressReporter,
) -> Analysis:
    """段を順に実行する。キーが一致して生成物が残っている段は飛ばす。"""
    run = _Run(recording, tools, settings, _Progress(report))
    audio_key = run.audio()
    segmentation, silence_key = run.segment(audio_key)
    run.proxy(audio_key)
    transcripts, transcribe_key = run.transcribe(silence_key, segmentation.chunks)
    tokens = run.align(transcribe_key, segmentation.chunks, transcripts)
    run.progress.start("finish")
    analysis = Analysis(
        recording_id=recording.id,
        silences=tuple(Silence(recording.id, span) for span in segmentation.silences),
        chunks=segmentation.chunks,
        tokens=tokens,
        suggestions=(
            *_silence_suggestions(recording.id, segmentation.silences),
            *detect_fillers(segmentation.chunks, tokens, min_gap_ms=settings.filler_min_gap_ms),
        ),
        review_marks=review_marks(
            recording.id,
            segmentation.chunks,
            transcripts,
            tokens,
            segmentation.speech,
            low_logprob=settings.low_confidence_logprob,
            min_unrecognized_ms=settings.min_unrecognized_ms,
        ),
    )
    save_analysis(tools.store, analysis)
    run.progress.done()
    return analysis


class _Progress:
    def __init__(self, report: ProgressReporter) -> None:
        self._report = report
        self._starts: dict[str, float] = {}
        total = 0.0
        for stage, weight in _WEIGHTS.items():
            self._starts[stage] = total
            total += weight

    def start(self, stage: str) -> None:
        self._report(stage, self._starts[stage])

    def within(self, stage: str) -> ProgressCallback:
        start, weight = self._starts[stage], _WEIGHTS[stage]
        return lambda fraction: self._report(stage, start + weight * min(max(fraction, 0.0), 1.0))

    def done(self) -> None:
        self._report("finish", 1.0)


class _Run:
    def __init__(
        self,
        recording: Recording,
        tools: AnalysisTools,
        settings: AnalysisSettings,
        progress: _Progress,
    ) -> None:
        self.recording = recording
        self.tools = tools
        self.settings = settings
        self.progress = progress
        self.source = require_source(recording)
        self.cache = StageCache(tools.store, recording.id)
        self.audio_path = tools.store.path(recording.id, AUDIO_FILE)

    def audio(self) -> str:
        key = stage_key(self.recording.fingerprint, "audio", _FORMAT_VERSION)
        self.progress.start("audio")
        if not self.cache.is_current("audio", key, AUDIO_FILE):
            self.tools.media.extract_audio(self.source, self.audio_path)
            self.cache.mark("audio", key)
        return key

    def segment(self, audio_key: str) -> tuple[_Segmentation, str]:
        s = self.settings
        settings = [s.silence_threshold_db, s.silence_min_ms, s.min_chunk_ms, _FORMAT_VERSION]
        key = stage_key(audio_key, "silence", settings)
        self.progress.start("silence")
        return self._json_stage(
            "silence", key, "silence.json", self._detect, self._segmentation
        ), key

    def _detect(self) -> ser.Json:
        s = self.settings
        volume = self.tools.media.detect_silences(
            self.audio_path, threshold_db=s.silence_threshold_db, min_ms=s.silence_min_ms
        )
        speech = self.tools.vad.detect_speech(self.audio_path)
        silences = find_silences(volume, speech, s.silence_min_ms)
        chunks = split_chunks(self.recording.duration_ms, silences, s.min_chunk_ms)
        return {
            "silences": [ser.span_to(x) for x in silences],
            "speech": [ser.span_to(x) for x in speech],
            "chunks": [ser.span_to(x) for x in chunks],
        }

    def _segmentation(self, data: ser.Json) -> _Segmentation:
        rid = self.recording.id
        return _Segmentation(
            silences=tuple(ser.span_from(x) for x in data["silences"]),
            speech=tuple(ser.span_from(x) for x in data["speech"]),
            chunks=tuple(
                SpeechChunk(id=f"{rid}-c{i:04d}", recording_id=rid, span=ser.span_from(span))
                for i, span in enumerate(data["chunks"])
            ),
        )

    def proxy(self, audio_key: str) -> None:
        self.progress.start("proxy")
        proxy_key = stage_key(self.recording.fingerprint, "proxy", _FORMAT_VERSION)
        if not self.cache.is_current("proxy", proxy_key, PROXY_FILE):
            self.tools.media.make_proxy(
                self.source,
                self.tools.store.path(self.recording.id, PROXY_FILE),
                duration_ms=self.recording.duration_ms,
                on_progress=self.progress.within("proxy"),
            )
            self.cache.mark("proxy", proxy_key)
        per_second = self.settings.peaks_per_second
        peaks_key = stage_key(audio_key, "peaks", per_second)
        self._json_stage(
            "peaks",
            peaks_key,
            PEAKS_FILE,
            lambda: ser.peaks_to(self.tools.media.compute_peaks(self.audio_path, per_second)),
            lambda data: data,
        )

    def transcribe(
        self, silence_key: str, chunks: tuple[SpeechChunk, ...]
    ) -> tuple[tuple[ChunkTranscript, ...], str]:
        hint = self.settings.transcribe_hint
        key = stage_key(silence_key, "transcribe", [hint, _FORMAT_VERSION])
        self.progress.start("transcribe")

        def compute() -> ser.Json:
            transcripts = self.tools.transcriber.transcribe(
                self.audio_path,
                [c.span for c in chunks],
                hint=hint,
                on_progress=self.progress.within("transcribe"),
            )
            return [ser.transcript_to(t) for t in transcripts]

        def decode(data: ser.Json) -> tuple[ChunkTranscript, ...]:
            transcripts = tuple(ser.transcript_from(t) for t in data)
            if len(transcripts) != len(chunks):
                raise ValueError("チャンクと文字起こしの数が合いません")
            return transcripts

        return self._json_stage("transcribe", key, "transcript.raw.json", compute, decode), key

    def align(
        self,
        transcribe_key: str,
        chunks: tuple[SpeechChunk, ...],
        transcripts: tuple[ChunkTranscript, ...],
    ) -> tuple[Token, ...]:
        key = stage_key(transcribe_key, "align", _FORMAT_VERSION)
        self.progress.start("align")

        def compute() -> ser.Json:
            segments = [(c.span, t.text) for c, t in zip(chunks, transcripts, strict=True)]
            aligned = self.tools.aligner.align(self.audio_path, segments)
            return [
                ser.token_to(token)
                for chunk, transcript, chars in zip(chunks, transcripts, aligned, strict=True)
                for token in build_tokens(chunk, transcript, chars)
            ]

        rid = self.recording.id
        return self._json_stage(
            "align",
            key,
            "transcript.json",
            compute,
            lambda data: tuple(ser.token_from(t, rid) for t in data),
        )

    def _json_stage[T](
        self,
        name: str,
        key: str,
        artifact: str,
        compute: Callable[[], ser.Json],
        decode: Callable[[ser.Json], T],
    ) -> T:
        """キーが一致して読める生成物があれば使い、なければ compute して保存する。"""
        rid = self.recording.id
        if self.cache.is_current(name, key, artifact):
            try:
                return ser.decode(self.tools.store.read_json(rid, artifact), decode)
            except ValueError:
                _logger.warning("%s の %s が壊れているため作り直します", rid, artifact)
        data = compute()
        self.tools.store.write_json(rid, artifact, data)
        self.cache.mark(name, key)
        return ser.decode(data, decode)


def _silence_suggestions(
    recording_id: str, silences: tuple[Interval, ...]
) -> tuple[CutSuggestion, ...]:
    return tuple(
        CutSuggestion(
            id=f"{recording_id}-silence-{i:04d}",
            recording_id=recording_id,
            span=span,
            kind=CutKind.SILENCE,
            reason=f"無音 {span.duration_ms / 1000:.1f} 秒",
        )
        for i, span in enumerate(silences)
    )
