"""API の出力スキーマ。載せる項目をここで決める（許可リスト方式。Design Doc 3-5-2）。

domain のオブジェクトをそのまま返さず、presenters.py が項目を 1 つずつ写す。
生のエラー文（Job.error、ImportFailure.message）を載せる項目は作らない。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from vidcut.domain.models import CutKind, ErrorCode, JobKind, JobStatus, ReviewMarkKind
from vidcut.services.lecture_views import LectureStatus


class FsEntryOut(BaseModel):
    name: str
    path: str
    kind: Literal["directory", "video"]


class FsListingOut(BaseModel):
    path: str
    parent: str | None  # ホームでは null（それより上へは行けない）
    entries: list[FsEntryOut]
    truncated: bool  # 件数が多く、残りを省いた


class RecordingOut(BaseModel):
    id: str
    name: str
    source_path: str
    duration_ms: int
    width: int
    height: int
    recorded_at: datetime | None


class ImportFailureOut(BaseModel):
    path: str
    code: ErrorCode
    message: str  # 種別ごとの定型文


class ImportResultOut(BaseModel):
    added: list[RecordingOut]
    existing: list[RecordingOut]
    failed: list[ImportFailureOut]


class JobOut(BaseModel):
    """error_message は種別ごとの定型文。生のエラー文は載せない。"""

    id: str
    kind: JobKind
    target_id: str
    status: JobStatus
    stage: str | None
    progress: float
    error_code: ErrorCode | None
    error_message: str | None


class JobListItemOut(JobOut):
    created_at: datetime
    updated_at: datetime


class LectureRefOut(BaseModel):
    id: str
    title: str
    recording_ids: list[str]


class LectureSummaryOut(BaseModel):
    id: str
    title: str
    status: LectureStatus
    recordings: list[RecordingOut]
    jobs: list[JobOut]  # 状態の根拠: 各録画ファイルの解析と、判定の、最新のジョブ


class SpanOut(BaseModel):
    start_ms: int
    end_ms: int


class ChunkOut(SpanOut):
    id: str


class TokenOut(SpanOut):
    id: str
    chunk_id: str
    text: str
    asr_confidence: float
    align_score: float


class SuggestionOut(SpanOut):
    """reason は言語モデルや規則が書いた文。画面でエスケープして表示すること。"""

    id: str
    recording_id: str
    kind: CutKind
    reason: str
    superseded_by: str | None


class ReviewMarkOut(SpanOut):
    kind: ReviewMarkKind


class RecordingDetailOut(RecordingOut):
    """解析結果つきの録画ファイル。解析がまだなら analyzed が false で、各一覧は空。

    analysis_unreadable が true のものは、解析結果が読めない（古い形・壊れている）。
    解析し直せば直る。
    """

    analyzed: bool
    analysis_unreadable: bool
    chunks: list[ChunkOut]
    tokens: list[TokenOut]
    silences: list[SpanOut]
    suggestions: list[SuggestionOut]  # 無音とフィラー
    review_marks: list[ReviewMarkOut]


class ManualCutOut(SpanOut):
    id: str
    recording_id: str


class EditStateOut(BaseModel):
    version: int
    restored_suggestion_ids: list[str]
    manual_cuts: list[ManualCutOut]


class DroppedRestoredOut(BaseModel):
    """通知を閉じたあとに残っている、引き継げなかった「戻した候補」。"""

    dropped_restored_ids: list[str]


class LectureDetailOut(BaseModel):
    """編集画面に必要なもの一式。

    実際に削除される区間は、recordings[].suggestions と judged_suggestions から
    戻したものを除き、manual_cuts を足したもの。
    judged が false なら判定はまだ（または失敗）で、無音とフィラーの候補だけがある。
    dropped_restored_ids は、判定のやり直しで引き継げなかった「戻した候補」（画面の通知用）。
    """

    id: str
    title: str
    status: LectureStatus
    jobs: list[JobOut]
    recordings: list[RecordingDetailOut]
    judged: bool
    judged_suggestions: list[SuggestionOut]
    dropped_restored_ids: list[str]
    edit_state: EditStateOut


class PeaksOut(BaseModel):
    """波形のピーク値。1 秒あたり per_second 個の 0〜1 の値。"""

    per_second: int
    values: list[float]
