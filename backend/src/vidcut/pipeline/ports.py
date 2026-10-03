"""外部ツールと永続化の抽象（Design Doc 3-1）。実装は adapters/ にあり、bootstrap.py が注入する。"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from vidcut.domain.models import EditState, Job, Lecture, MediaInfo, Recording


class ExternalToolError(RuntimeError):
    """ffmpeg などの外部ツールが見つからない・失敗した。"""


class UnsupportedMediaError(ValueError):
    """録画ファイルが処理できない形式（映像または音声のトラックがない等）。"""


class NotFoundError(LookupError):
    """指定した id のデータが保存されていない。"""


class VersionConflictError(RuntimeError):
    """編集状態の保存で、版が保存済みのものと一致しない（楽観的排他）。"""


ProgressCallback = Callable[[float], None]
"""長い処理の進捗（0〜1）を受け取る。"""


@dataclass(frozen=True)
class ProbeResult:
    """録画ファイルの情報。duration_ms は音声の終わり（タイムラインの長さ）。"""

    media: MediaInfo
    duration_ms: int
    recorded_at: datetime | None


@dataclass(frozen=True)
class Peaks:
    """波形の表示用のピーク値。1 秒あたり per_second 個の 0〜1 の値。"""

    per_second: int
    values: tuple[float, ...]


class MediaTool(Protocol):
    def probe(self, source: Path) -> ProbeResult: ...

    def extract_audio(self, source: Path, dest: Path) -> None:
        """解析用の音声（16kHz モノラル wav）。先頭はタイムラインの 0 秒にそろえる。"""
        ...

    def make_proxy(
        self, source: Path, dest: Path, *, duration_ms: int, on_progress: ProgressCallback | None
    ) -> None:
        """ブラウザでのプレビュー用の軽い動画。"""
        ...

    def make_mezzanine(
        self, source: Path, dest: Path, *, duration_ms: int, on_progress: ProgressCallback | None
    ) -> None:
        """書き出し用の固定フレームレートの中間素材（ADR-002）。"""
        ...

    def compute_peaks(self, audio: Path, per_second: int) -> Peaks:
        """extract_audio で作った wav から波形のピーク値を求める。"""
        ...


class RecordingRepository(Protocol):
    def add(self, recording: Recording) -> None: ...

    def get(self, recording_id: str) -> Recording | None: ...

    def find_by_fingerprint(self, fingerprint: str) -> Recording | None: ...

    def list_all(self) -> tuple[Recording, ...]: ...


class LectureRepository(Protocol):
    def get(self, lecture_id: str) -> Lecture | None: ...

    def find_by_recording(self, recording_id: str) -> Lecture | None: ...

    def list_all(self) -> tuple[Lecture, ...]: ...

    def save(self, lecture: Lecture) -> None: ...

    def delete(self, lecture_id: str) -> None: ...

    def replace(self, *, remove: Iterable[str], save: Iterable[Lecture]) -> None:
        """削除と保存を 1 つのトランザクションで行う（まとめる・解除）。"""
        ...


class EditStateRepository(Protocol):
    def get(self, lecture_id: str) -> EditState:
        """保存されていなければ version 0 の空の状態を返す。"""
        ...

    def save(self, state: EditState) -> EditState:
        """state.version が保存済みの版と一致すれば保存し、version を 1 進めた状態を返す。"""
        ...


@dataclass(frozen=True)
class StoredJob:
    job: Job
    priority: int
    created_at: datetime
    updated_at: datetime


class JobQueue(Protocol):
    def enqueue(self, job: Job) -> None: ...

    def get(self, job_id: str) -> StoredJob | None: ...

    def list_all(self) -> tuple[StoredJob, ...]: ...

    def claim_next(self) -> Job | None:
        """待機中のジョブのうち、優先度が高く、先に登録されたものを実行中にして返す。"""
        ...

    def report_progress(self, job_id: str, stage: str | None, progress: float) -> None: ...

    def mark_succeeded(self, job_id: str) -> None: ...

    def mark_failed(self, job_id: str, error: str) -> None: ...

    def requeue_running(self) -> int:
        """実行中のまま残ったジョブを待機中に戻し、その件数を返す（起動時の復旧）。"""
        ...

    def retry(self, job_id: str) -> None:
        """失敗したジョブを待機中に戻す。"""
        ...
