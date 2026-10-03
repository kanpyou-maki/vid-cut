"""vid-cut のデータモデル（Design Doc 4 章）。すべて不変で、変更は新しいオブジェクトを返す。"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from vidcut.domain.intervals import Interval


def _require_unit_range(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} は 0 以上 1 以下である必要があります: {value}")


@dataclass(frozen=True)
class MediaInfo:
    width: int
    height: int
    is_vfr: bool
    avg_fps: float
    audio_rate: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"解像度が不正です: {self.width}x{self.height}")
        if self.avg_fps <= 0 or self.audio_rate <= 0:
            raise ValueError(f"フレームレートまたはサンプルレートが不正です: {self}")


@dataclass(frozen=True)
class Recording:
    """1 回の録画で生まれる mov ファイル。"""

    id: str
    source_path: str
    fingerprint: str
    duration_ms: int
    recorded_at: datetime | None
    media: MediaInfo

    def __post_init__(self) -> None:
        if self.duration_ms <= 0:
            raise ValueError(f"duration_ms は正である必要があります: {self.duration_ms}")


@dataclass(frozen=True)
class SpeechChunk:
    """無音で区切った発話のまとまり。"""

    id: str
    recording_id: str
    span: Interval


@dataclass(frozen=True)
class Token:
    """文字起こしの最小単位（日本語では 1 文字が基本）。"""

    id: str
    recording_id: str
    chunk_id: str
    text: str
    span: Interval
    asr_confidence: float
    align_score: float

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("text は空にできません")
        _require_unit_range("asr_confidence", self.asr_confidence)
        _require_unit_range("align_score", self.align_score)


@dataclass(frozen=True)
class Silence:
    recording_id: str
    span: Interval


@dataclass(frozen=True)
class Lecture:
    """編集と書き出しの単位。順序付きの 1 本以上の録画ファイルで構成される。"""

    id: str
    title: str
    recording_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.recording_ids:
            raise ValueError("レクチャーには録画ファイルが 1 本以上必要です")
        if len(set(self.recording_ids)) != len(self.recording_ids):
            raise ValueError(f"録画ファイルが重複しています: {self.recording_ids}")

    def reordered(self, recording_ids: tuple[str, ...]) -> "Lecture":
        if sorted(recording_ids) != sorted(self.recording_ids):
            raise ValueError("並べ替えでは録画ファイルの構成を変えられません")
        return replace(self, recording_ids=recording_ids)


class CutKind(StrEnum):
    SILENCE = "silence"
    FILLER = "filler"
    RETAKE = "retake"
    MISSPEAK = "misspeak"
    NOISE = "noise"

    @property
    def is_rejudged(self) -> bool:
        """言い直しの判定（レクチャー単位）で作り直される種類か。"""
        return self in {CutKind.RETAKE, CutKind.MISSPEAK, CutKind.NOISE}


@dataclass(frozen=True)
class CutSuggestion:
    """自動で検出した削除候補。"""

    id: str
    recording_id: str
    span: Interval
    kind: CutKind
    reason: str
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if self.kind.is_rejudged and not self.reason:
            raise ValueError(f"{self.kind} の削除候補には理由が必要です（US-05）")


@dataclass(frozen=True)
class ManualCut:
    """人が追加した削除区間。"""

    id: str
    recording_id: str
    span: Interval


@dataclass(frozen=True)
class EditState:
    """レクチャーの編集状態。version は永続化層が楽観的排他に使う。"""

    lecture_id: str
    version: int
    restored_suggestion_ids: frozenset[str] = field(default_factory=frozenset)
    manual_cuts: tuple[ManualCut, ...] = ()

    def __post_init__(self) -> None:
        if self.version < 0:
            raise ValueError(f"version は 0 以上である必要があります: {self.version}")

    def restore(self, suggestion_id: str) -> "EditState":
        return replace(self, restored_suggestion_ids=self.restored_suggestion_ids | {suggestion_id})

    def unrestore(self, suggestion_id: str) -> "EditState":
        return replace(self, restored_suggestion_ids=self.restored_suggestion_ids - {suggestion_id})

    def add_manual_cut(self, cut: ManualCut) -> "EditState":
        if any(c.id == cut.id for c in self.manual_cuts):
            raise ValueError(f"同じ id の削除区間が既にあります: {cut.id}")
        return replace(self, manual_cuts=(*self.manual_cuts, cut))

    def remove_manual_cut(self, cut_id: str) -> "EditState":
        return replace(self, manual_cuts=tuple(c for c in self.manual_cuts if c.id != cut_id))


class ReviewMarkKind(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    UNRECOGNIZED_SPEECH = "unrecognized_speech"


@dataclass(frozen=True)
class ReviewMark:
    """人が耳で確認すべき箇所の印（US-04）。"""

    recording_id: str
    span: Interval
    kind: ReviewMarkKind


class JobKind(StrEnum):
    ANALYZE_RECORDING = "analyze_recording"
    MAKE_MEZZANINE = "make_mezzanine"
    JUDGE_LECTURE = "judge_lecture"
    EXPORT_PREMIERE = "export_premiere"
    EXPORT_MP4 = "export_mp4"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class Job:
    id: str
    kind: JobKind
    target_id: str
    status: JobStatus = JobStatus.QUEUED
    stage: str | None = None
    progress: float = 0.0
    error: str | None = None

    def __post_init__(self) -> None:
        _require_unit_range("progress", self.progress)
