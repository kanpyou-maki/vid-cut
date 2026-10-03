"""API の入出力スキーマ。入力は厳格な型と上限で受け、出力は載せる項目をここで決める。

出力は許可リスト方式: domain のオブジェクトをそのまま返さず、項目を 1 つずつ写す。
生のエラー文（Job.error、ImportFailure.message）は写さない（Design Doc 3-5-2）。
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

from vidcut.api.messages import ERROR_MESSAGES, error_message
from vidcut.domain.intervals import Interval
from vidcut.domain.models import (
    CutKind,
    CutSuggestion,
    EditState,
    ErrorCode,
    Job,
    JobKind,
    JobStatus,
    Lecture,
    ManualCut,
    Recording,
    ReviewMarkKind,
    Token,
)
from vidcut.domain.titles import MAX_TITLE_CHARS
from vidcut.pipeline.analysis_result import Analysis
from vidcut.pipeline.ports import StoredJob
from vidcut.services.file_browser import Entry, Listing
from vidcut.services.imports import ImportFailure, ImportResult
from vidcut.services.lecture_views import JobView, LectureDetail, LectureStatus, LectureSummary

# --- 入力の上限（M1 のセキュリティレビュー。Design Doc 3-5）
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
MAX_SUGGESTION_ID_CHARS = 100
MAX_PATH_CHARS = 4096
MAX_IMPORT_PATHS = 200
MAX_LECTURE_RECORDINGS = 50
MAX_MANUAL_CUTS = 2000
MAX_RESTORED_SUGGESTIONS = 20_000
MAX_TIME_MS = 24 * 60 * 60 * 1000
"""録画ファイル内の時刻の上限（24 時間）。"""

Id = Annotated[str, StringConstraints(pattern=ID_PATTERN)]
SuggestionId = Annotated[str, StringConstraints(min_length=1, max_length=MAX_SUGGESTION_ID_CHARS)]
PathText = Annotated[str, StringConstraints(min_length=1, max_length=MAX_PATH_CHARS)]
TimeMs = Annotated[StrictInt, Field(ge=0, le=MAX_TIME_MS)]


class _Input(BaseModel):
    """型を読み替えない（"1" や 1.0 を整数として受け付けない）。知らない項目は拒む。"""

    model_config = ConfigDict(strict=True, extra="forbid")


class ImportIn(_Input):
    paths: Annotated[list[PathText], Field(min_length=1, max_length=MAX_IMPORT_PATHS)]


class MergeIn(_Input):
    lecture_ids: Annotated[list[Id], Field(min_length=2, max_length=MAX_LECTURE_RECORDINGS)]
    # 長すぎる題名は、黙って切り詰めずに拒む
    title: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TITLE_CHARS)] | None = None


class OrderIn(_Input):
    recording_ids: Annotated[list[Id], Field(min_length=1, max_length=MAX_LECTURE_RECORDINGS)]


class ManualCutIn(_Input):
    id: Id
    recording_id: Id
    start_ms: TimeMs
    end_ms: TimeMs

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms は start_ms より大きい必要があります")
        return self

    def to_domain(self) -> ManualCut:
        return ManualCut(
            id=self.id,
            recording_id=self.recording_id,
            span=Interval(self.start_ms, self.end_ms),
        )


class EditsIn(_Input):
    version: Annotated[StrictInt, Field(ge=0)]
    restored_suggestion_ids: Annotated[
        list[SuggestionId], Field(max_length=MAX_RESTORED_SUGGESTIONS)
    ]
    manual_cuts: Annotated[list[ManualCutIn], Field(max_length=MAX_MANUAL_CUTS)]

    def to_domain(self, lecture_id: str) -> EditState:
        return EditState(
            lecture_id=lecture_id,
            version=self.version,
            restored_suggestion_ids=frozenset(self.restored_suggestion_ids),
            manual_cuts=tuple(cut.to_domain() for cut in self.manual_cuts),
        )


class ExportIn(_Input):
    format: Literal["premiere_xml", "mp4"]

    def job_kind(self) -> JobKind:
        return JobKind.EXPORT_PREMIERE if self.format == "premiere_xml" else JobKind.EXPORT_MP4


# --- 出力


class FsEntryOut(BaseModel):
    name: str
    path: str
    kind: Literal["directory", "video"]

    @classmethod
    def of(cls, entry: Entry) -> Self:
        kind: Literal["directory", "video"] = "directory" if entry.is_directory else "video"
        return cls(name=entry.name, path=str(entry.path), kind=kind)


class FsListingOut(BaseModel):
    path: str
    parent: str | None
    entries: list[FsEntryOut]
    truncated: bool

    @classmethod
    def of(cls, listing: Listing) -> Self:
        return cls(
            path=str(listing.path),
            parent=None if listing.parent is None else str(listing.parent),
            entries=[FsEntryOut.of(entry) for entry in listing.entries],
            truncated=listing.truncated,
        )


class RecordingOut(BaseModel):
    id: str
    name: str
    source_path: str
    duration_ms: int
    width: int
    height: int
    recorded_at: datetime | None

    @classmethod
    def of(cls, recording: Recording) -> "RecordingOut":
        return RecordingOut(
            id=recording.id,
            name=Path(recording.source_path).name,
            source_path=recording.source_path,
            duration_ms=recording.duration_ms,
            width=recording.media.width,
            height=recording.media.height,
            recorded_at=recording.recorded_at,
        )


class ImportFailureOut(BaseModel):
    path: str
    code: ErrorCode
    message: str  # 種別ごとの定型文

    @classmethod
    def of(cls, failure: ImportFailure) -> Self:
        return cls(path=failure.path, code=failure.code, message=ERROR_MESSAGES[failure.code])


class ImportResultOut(BaseModel):
    added: list[RecordingOut]
    existing: list[RecordingOut]
    failed: list[ImportFailureOut]

    @classmethod
    def of(cls, result: ImportResult, refused: list[ImportFailureOut]) -> Self:
        return cls(
            added=[RecordingOut.of(recording) for recording in result.added],
            existing=[RecordingOut.of(recording) for recording in result.existing],
            failed=[*refused, *(ImportFailureOut.of(failure) for failure in result.failed)],
        )


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

    @classmethod
    def of(cls, job: Job | JobView) -> "JobOut":
        failed = job.status is JobStatus.FAILED
        return JobOut(
            id=job.id,
            kind=job.kind,
            target_id=job.target_id,
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            # 種別が記録される前（古い版）の失敗は internal として扱う
            error_code=(job.error_code or ErrorCode.INTERNAL) if failed else None,
            error_message=error_message(job.error_code, failed=failed),
        )


class JobListItemOut(JobOut):
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of_stored(cls, stored: StoredJob) -> Self:
        return cls(
            **JobOut.of(stored.job).model_dump(),
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )


class LectureRefOut(BaseModel):
    id: str
    title: str
    recording_ids: list[str]

    @classmethod
    def of(cls, lecture: Lecture) -> Self:
        return cls(id=lecture.id, title=lecture.title, recording_ids=list(lecture.recording_ids))


class LectureSummaryOut(BaseModel):
    id: str
    title: str
    status: LectureStatus
    recordings: list[RecordingOut]
    jobs: list[JobOut]  # 状態の根拠: 各録画ファイルの解析と、判定の、最新のジョブ

    @classmethod
    def of(cls, summary: LectureSummary) -> Self:
        return cls(
            id=summary.lecture.id,
            title=summary.lecture.title,
            status=summary.status,
            recordings=[RecordingOut.of(recording) for recording in summary.recordings],
            jobs=[JobOut.of(job) for job in summary.jobs],
        )


class SpanOut(BaseModel):
    start_ms: int
    end_ms: int

    @classmethod
    def of(cls, span: Interval) -> Self:
        return cls(start_ms=span.start_ms, end_ms=span.end_ms)


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

    @classmethod
    def of_suggestion(cls, suggestion: CutSuggestion) -> Self:
        return cls(
            id=suggestion.id,
            recording_id=suggestion.recording_id,
            start_ms=suggestion.span.start_ms,
            end_ms=suggestion.span.end_ms,
            kind=suggestion.kind,
            reason=suggestion.reason,
            superseded_by=suggestion.superseded_by,
        )


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

    @classmethod
    def of_detail(
        cls, recording: Recording, analysis: Analysis | None, *, unreadable: bool
    ) -> Self:
        return cls(
            **RecordingOut.of(recording).model_dump(),
            analyzed=analysis is not None,
            analysis_unreadable=unreadable,
            chunks=[
                ChunkOut(id=c.id, start_ms=c.span.start_ms, end_ms=c.span.end_ms)
                for c in (analysis.chunks if analysis else ())
            ],
            tokens=[_token(t) for t in (analysis.tokens if analysis else ())],
            silences=[SpanOut.of(s.span) for s in (analysis.silences if analysis else ())],
            suggestions=[
                SuggestionOut.of_suggestion(s) for s in (analysis.suggestions if analysis else ())
            ],
            review_marks=[
                ReviewMarkOut(start_ms=m.span.start_ms, end_ms=m.span.end_ms, kind=m.kind)
                for m in (analysis.review_marks if analysis else ())
            ],
        )


def _token(token: Token) -> TokenOut:
    return TokenOut(
        id=token.id,
        chunk_id=token.chunk_id,
        text=token.text,
        start_ms=token.span.start_ms,
        end_ms=token.span.end_ms,
        asr_confidence=token.asr_confidence,
        align_score=token.align_score,
    )


class ManualCutOut(SpanOut):
    id: str
    recording_id: str


class EditStateOut(BaseModel):
    version: int
    restored_suggestion_ids: list[str]
    manual_cuts: list[ManualCutOut]

    @classmethod
    def of(cls, state: EditState) -> Self:
        return cls(
            version=state.version,
            restored_suggestion_ids=sorted(state.restored_suggestion_ids),
            manual_cuts=[
                ManualCutOut(
                    id=cut.id,
                    recording_id=cut.recording_id,
                    start_ms=cut.span.start_ms,
                    end_ms=cut.span.end_ms,
                )
                for cut in state.manual_cuts
            ],
        )


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

    @classmethod
    def of(cls, detail: LectureDetail) -> Self:
        summary = detail.summary
        judgement = detail.judgement
        return cls(
            id=summary.lecture.id,
            title=summary.lecture.title,
            status=summary.status,
            jobs=[JobOut.of(job) for job in summary.jobs],
            recordings=[
                RecordingDetailOut.of_detail(
                    recording,
                    detail.analyses.get(recording.id),
                    unreadable=recording.id in detail.unreadable_recording_ids,
                )
                for recording in summary.recordings
            ],
            judged=judgement is not None,
            judged_suggestions=[
                SuggestionOut.of_suggestion(s) for s in (judgement.suggestions if judgement else ())
            ],
            dropped_restored_ids=list(judgement.dropped_restored_ids) if judgement else [],
            edit_state=EditStateOut.of(detail.edit_state),
        )


class PeaksOut(BaseModel):
    """波形のピーク値。1 秒あたり per_second 個の 0〜1 の値。"""

    per_second: int
    values: list[float]
