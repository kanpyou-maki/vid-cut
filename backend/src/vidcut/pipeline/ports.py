"""外部ツールと永続化の抽象（Design Doc 3-1）。実装は adapters/ にあり、bootstrap.py が注入する。"""

from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from vidcut.domain.intervals import Interval
from vidcut.domain.models import (
    CutSuggestion,
    EditState,
    ErrorCode,
    Job,
    Lecture,
    MediaInfo,
    Recording,
)
from vidcut.domain.timeline import FrameRange


class ExternalToolError(RuntimeError):
    """ffmpeg などの外部ツールが見つからない・失敗した。"""


class LoginRequiredError(ExternalToolError):
    """`claude` にログインしていない。利用者が `/login` を実行する必要がある。"""


class UnsupportedMediaError(ValueError):
    """録画ファイルが処理できない形式（映像または音声のトラックがない等）。"""


class NothingToExportError(ValueError):
    """書き出そうとしたレクチャーに、残す区間が 1 つもない。"""


class InvalidInputError(ValueError):
    """利用者の入力を受け付けられない（API では 422 で返す）。

    この例外の文は、そのまま画面に出る。入力のどこが誤りかを説明する文だけを書き、
    絶対パスや、ほかの例外・外部ツールの文を入れないこと（Design Doc 3-5-2）。
    """


class NotFoundError(LookupError):
    """指定した id のデータが保存されていない。"""


class VersionConflictError(RuntimeError):
    """編集状態の保存で、版が保存済みのものと一致しない（楽観的排他）。"""


ProgressCallback = Callable[[float], None]
"""長い処理の進捗（0〜1）を受け取る。"""

ProgressReporter = Callable[[str | None, float], None]
"""ジョブの処理中の段の名前と、ジョブ全体の進捗（0〜1）を知らせる。"""


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


@dataclass(frozen=True)
class MediaClip:
    """中間素材から切り出す 1 区間。frames は中間素材のフレーム番号。"""

    source: Path
    frames: FrameRange


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

    def export_mp4(
        self,
        clips: Sequence[MediaClip],
        dest: Path,
        *,
        fps: int,
        on_progress: ProgressCallback | None,
    ) -> None:
        """中間素材（フレームレートは fps）から clips を切り出し、順につないだ MP4 を作る。"""
        ...

    def compute_peaks(self, audio: Path, per_second: int) -> Peaks:
        """extract_audio で作った wav から波形のピーク値を求める。"""
        ...

    def detect_silences(
        self, audio: Path, *, threshold_db: float, min_ms: int
    ) -> tuple[Interval, ...]:
        """音量が threshold_db 未満の状態が min_ms 以上続く区間。"""
        ...


class VoiceActivityDetector(Protocol):
    def detect_speech(self, audio: Path) -> tuple[Interval, ...]:
        """解析用の wav から、人の声がある区間を返す。"""
        ...


@dataclass(frozen=True)
class ChunkTranscript:
    """発話チャンク 1 つの文字起こし。avg_logprob は確信度の目安（0 に近いほど高い）。"""

    text: str
    avg_logprob: float


class Transcriber(Protocol):
    model_id: str
    """モデルの識別子。生成物のキャッシュのキーに入れる（モデルを変えたら作り直す）。"""

    def transcribe(
        self,
        audio: Path,
        spans: Sequence[Interval],
        *,
        hint: str,
        on_progress: ProgressCallback | None,
    ) -> tuple[ChunkTranscript, ...]:
        """spans の各区間を個別に文字起こしし、同じ順で返す。"""
        ...


@dataclass(frozen=True)
class AlignedChar:
    """位置合わせした 1 文字。時刻が付かなかった文字は start_ms / end_ms が None。"""

    text: str
    start_ms: int | None
    end_ms: int | None
    score: float | None


class Aligner(Protocol):
    model_id: str
    """モデルの識別子。生成物のキャッシュのキーに入れる。"""

    def align(
        self, audio: Path, segments: Sequence[tuple[Interval, str]]
    ) -> tuple[tuple[AlignedChar, ...], ...]:
        """各区間の文字列に文字単位の時刻（録画ファイル内のミリ秒）を付け、同じ順で返す。"""
        ...


class LanguageModel(Protocol):
    def complete(self, prompt: str) -> str:
        """指示文を渡し、応答の文章を返す。ツールは使わせない（Design Doc 3-3）。"""
        ...


class ArtifactStore(Protocol):
    """録画ファイルごとの生成物（ワークスペースのファイル）。"""

    def path(self, recording_id: str, name: str) -> Path:
        """生成物のファイルの場所。親のディレクトリは作っておく。"""
        ...

    def read_json(self, recording_id: str, name: str) -> object | None:
        """保存されていなければ None。"""
        ...

    def write_json(self, recording_id: str, name: str, data: object) -> None:
        """書き終えてから置き換える（途中の状態を残さない）。"""
        ...


class ExportStore(Protocol):
    """書き出し先。ワークスペースの exports/<レクチャー名>/<レクチャー名><suffix>。"""

    def path(self, title: str, suffix: str) -> Path:
        """書き出すファイルの場所。親のディレクトリは作っておく。"""
        ...

    def write_text(self, title: str, suffix: str, text: str) -> Path:
        """書き終えてから置き換え、書いたファイルの場所を返す。"""
        ...


Atomic = Callable[[], AbstractContextManager[None]]
"""`with atomic():` で囲んだ保存をまとめて確定する。途中で例外が出たら、囲んだ保存をすべて取り消す。

複数のリポジトリやジョブ表にまたがる保存に使う（Design Doc 3-5-2）。
"""

Fingerprinter = Callable[[Path], str]
"""録画ファイルの同一性の判定に使う値（サイズ + 更新日時 + 先頭と末尾のハッシュ）。"""


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
class Judgement:
    """レクチャーの言い直しの判定結果。input_key は判定に渡した入力のハッシュ。"""

    lecture_id: str
    input_key: str
    suggestions: tuple[CutSuggestion, ...]  # retake / misspeak / noise
    dropped_restored_ids: tuple[str, ...] = ()  # 判定のやり直しで引き継げなかった「戻した候補」


class JudgementRepository(Protocol):
    def get(self, lecture_id: str) -> Judgement | None:
        """まだ判定していなければ None。"""
        ...

    def save(self, judgement: Judgement) -> None:
        """レクチャーの判定結果を置き換える。"""
        ...

    def dismiss_dropped(self, lecture_id: str, ids: frozenset[str]) -> tuple[str, ...]:
        """引き継げなかった「戻した候補」の記録から ids だけを消し、残りを返す。

        読み取りと書き込みを 1 つにまとめて行う（途中で判定がやり直されても、その結果を古い内容で
        上書きしない）。判定結果がなければ、何もせずに空を返す。
        """
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

    def mark_failed(self, job_id: str, error: str, code: ErrorCode) -> None:
        """error は生のエラー文、code はその種別（画面に出すのは code だけ）。"""
        ...

    def requeue_running(self) -> int:
        """実行中のまま残ったジョブを待機中に戻し、その件数を返す（起動時の復旧）。"""
        ...

    def retry(self, job_id: str) -> None:
        """失敗したジョブを待機中に戻す。"""
        ...

    def discard_queued_for(self, target_ids: Iterable[str]) -> int:
        """target_ids のどれかを対象にした待機中のジョブを消し、その件数を返す。

        レクチャーをまとめる・解除するときに、なくなるレクチャーの判定や書き出しを消すのに使う。
        """
        ...
