"""pipeline のテスト用の偽の ports。呼ばれた回数を数え、決まった結果を返す。"""

import json
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from vidcut.domain.intervals import Interval
from vidcut.domain.models import MediaInfo, Recording
from vidcut.pipeline.ports import (
    AlignedChar,
    ChunkTranscript,
    Peaks,
    ProbeResult,
    ProgressCallback,
)

DURATION_MS = 10_000
MEDIA = MediaInfo(width=1920, height=1080, is_vfr=True, avg_fps=3.2, audio_rate=48_000)


def make_recording(source: Path, rid: str = "r1") -> Recording:
    return Recording(
        id=rid,
        source_path=str(source),
        fingerprint=f"fp-{rid}",
        duration_ms=DURATION_MS,
        recorded_at=datetime(2026, 9, 10, tzinfo=UTC),
        media=MEDIA,
    )


class FakeMediaTool:
    """無音は 0〜1 / 4〜5 / 9〜10 秒。発話は 1〜4 秒と 5〜9 秒。"""

    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.silences = (Interval(0, 1_000), Interval(4_000, 5_000), Interval(9_000, 10_000))

    def probe(self, source: Path) -> ProbeResult:
        self.calls["probe"] += 1
        return ProbeResult(media=MEDIA, duration_ms=DURATION_MS, recorded_at=None)

    def extract_audio(self, source: Path, dest: Path) -> None:
        self.calls["extract_audio"] += 1
        dest.write_bytes(b"wav")

    def make_proxy(
        self, source: Path, dest: Path, *, duration_ms: int, on_progress: ProgressCallback | None
    ) -> None:
        self.calls["make_proxy"] += 1
        dest.write_bytes(b"proxy")

    def make_mezzanine(
        self, source: Path, dest: Path, *, duration_ms: int, on_progress: ProgressCallback | None
    ) -> None:
        self.calls["make_mezzanine"] += 1
        if on_progress:
            on_progress(0.5)
        dest.write_bytes(b"mezzanine")

    def compute_peaks(self, audio: Path, per_second: int) -> Peaks:
        self.calls["compute_peaks"] += 1
        return Peaks(per_second=per_second, values=(0.0, 0.5, 1.0))

    def detect_silences(
        self, audio: Path, *, threshold_db: float, min_ms: int
    ) -> tuple[Interval, ...]:
        self.calls["detect_silences"] += 1
        return self.silences


class FakeVad:
    def __init__(self) -> None:
        self.calls = 0

    def detect_speech(self, audio: Path) -> tuple[Interval, ...]:
        self.calls += 1
        # 6.5〜8.5 秒は発話だが、文字起こしでは何も割り当たらない
        return (Interval(1_000, 4_000), Interval(5_000, 6_000), Interval(6_500, 8_500))


class FakeTranscriber:
    TEXTS = ("えーと", "こんにちは")
    LOGPROBS = (-0.1, -0.8)

    def __init__(self) -> None:
        self.calls = 0
        self.hints: list[str] = []

    def transcribe(
        self,
        audio: Path,
        spans: Sequence[Interval],
        *,
        hint: str,
        on_progress: ProgressCallback | None,
    ) -> tuple[ChunkTranscript, ...]:
        self.calls += 1
        self.hints.append(hint)
        if on_progress:
            on_progress(1.0)
        return tuple(
            ChunkTranscript(text, logprob)
            for text, logprob, _ in zip(self.TEXTS, self.LOGPROBS, spans, strict=True)
        )


class FakeAligner:
    """1 文字 100ms で、区間の先頭から並べる。"""

    def __init__(self) -> None:
        self.calls = 0

    def align(
        self, audio: Path, segments: Sequence[tuple[Interval, str]]
    ) -> tuple[tuple[AlignedChar, ...], ...]:
        self.calls += 1
        return tuple(
            tuple(
                AlignedChar(ch, span.start_ms + i * 100, span.start_ms + (i + 1) * 100, 0.9)
                for i, ch in enumerate(text)
            )
            for span, text in segments
        )


class DirectoryStore:
    """ArtifactStore の最小の実装（tmp_path の下）。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, recording_id: str, name: str) -> Path:
        directory = self.root / recording_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory / name

    def read_json(self, recording_id: str, name: str) -> object | None:
        file = self.root / recording_id / name
        return json.loads(file.read_text()) if file.exists() else None

    def write_json(self, recording_id: str, name: str, data: object) -> None:
        self.path(recording_id, name).write_text(json.dumps(data, ensure_ascii=False))
