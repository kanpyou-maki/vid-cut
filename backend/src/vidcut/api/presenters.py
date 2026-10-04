"""domain と services の結果を、出力スキーマ（outputs.py）に写す。

項目は名前を挙げて 1 つずつ写す（載せる項目を型で確かめられるようにする）。
生のエラー文（Job.error、ImportFailure.message）は写さず、種別ごとの定型文に置き換える。
"""

from collections.abc import Sequence
from pathlib import Path

from vidcut.api.messages import ERROR_MESSAGES, error_message
from vidcut.api.outputs import (
    ChunkOut,
    EditStateOut,
    ExportFileOut,
    ExportsOut,
    FsEntryOut,
    FsListingOut,
    ImportFailureOut,
    ImportResultOut,
    JobListItemOut,
    JobOut,
    KeepPaddingOut,
    LectureDetailOut,
    LectureRefOut,
    LectureSummaryOut,
    ManualCutOut,
    PeaksOut,
    RecordingDetailOut,
    RecordingOut,
    ReviewMarkOut,
    SettingsOut,
    SpanOut,
    SuggestionOut,
    TokenOut,
)
from vidcut.domain.models import (
    CutSuggestion,
    EditState,
    ErrorCode,
    Job,
    JobStatus,
    Lecture,
    Recording,
    Token,
)
from vidcut.domain.timeline import KeepPadding
from vidcut.pipeline.analysis_result import Analysis
from vidcut.pipeline.export import ExportSettings
from vidcut.pipeline.ports import Peaks, StoredJob
from vidcut.services.export_destinations import ExportFileStatus, ExportStatus
from vidcut.services.file_browser import Listing
from vidcut.services.imports import ImportResult
from vidcut.services.lecture_views import JobView, LectureDetail, LectureSummary
from vidcut.services.settings import SettingsView


def to_fs_listing(listing: Listing) -> FsListingOut:
    return FsListingOut(
        path=str(listing.path),
        parent=None if listing.parent is None else str(listing.parent),
        entries=[
            FsEntryOut(
                name=entry.name,
                path=str(entry.path),
                kind="directory" if entry.is_directory else "video",
            )
            for entry in listing.entries
        ],
        truncated=listing.truncated,
    )


def to_recording(recording: Recording) -> RecordingOut:
    return RecordingOut(
        id=recording.id,
        name=Path(recording.source_path).name,
        source_path=recording.source_path,
        duration_ms=recording.duration_ms,
        width=recording.media.width,
        height=recording.media.height,
        recorded_at=recording.recorded_at,
    )


def to_import_failure(path: str, code: ErrorCode) -> ImportFailureOut:
    return ImportFailureOut(path=path, code=code, message=ERROR_MESSAGES[code])


def to_import_result(result: ImportResult, missing: Sequence[ImportFailureOut]) -> ImportResultOut:
    """missing は、取り込みの前に見つからなかったパス。"""
    return ImportResultOut(
        added=[to_recording(recording) for recording in result.added],
        existing=[to_recording(recording) for recording in result.existing],
        failed=[*missing, *(to_import_failure(f.path, f.code) for f in result.failed)],
    )


def to_job(job: Job | JobView) -> JobOut:
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


def to_job_list_item(stored: StoredJob) -> JobListItemOut:
    job = to_job(stored.job)
    return JobListItemOut(
        id=job.id,
        kind=job.kind,
        target_id=job.target_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


def to_lecture_ref(lecture: Lecture) -> LectureRefOut:
    return LectureRefOut(
        id=lecture.id, title=lecture.title, recording_ids=list(lecture.recording_ids)
    )


def to_lecture_summary(summary: LectureSummary) -> LectureSummaryOut:
    return LectureSummaryOut(
        id=summary.lecture.id,
        title=summary.lecture.title,
        status=summary.status,
        recordings=[to_recording(recording) for recording in summary.recordings],
        jobs=[to_job(job) for job in summary.jobs],
    )


def to_suggestion(suggestion: CutSuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=suggestion.id,
        recording_id=suggestion.recording_id,
        start_ms=suggestion.span.start_ms,
        end_ms=suggestion.span.end_ms,
        kind=suggestion.kind,
        reason=suggestion.reason,
        superseded_by=suggestion.superseded_by,
    )


def to_token(token: Token) -> TokenOut:
    return TokenOut(
        id=token.id,
        chunk_id=token.chunk_id,
        text=token.text,
        start_ms=token.span.start_ms,
        end_ms=token.span.end_ms,
        asr_confidence=token.asr_confidence,
        align_score=token.align_score,
    )


def to_recording_detail(
    recording: Recording, analysis: Analysis | None, *, unreadable: bool
) -> RecordingDetailOut:
    """解析がまだ（または読めない）なら、各一覧は空。"""
    base = to_recording(recording)
    return RecordingDetailOut(
        id=base.id,
        name=base.name,
        source_path=base.source_path,
        duration_ms=base.duration_ms,
        width=base.width,
        height=base.height,
        recorded_at=base.recorded_at,
        analyzed=analysis is not None,
        analysis_unreadable=unreadable,
        chunks=[
            ChunkOut(id=c.id, start_ms=c.span.start_ms, end_ms=c.span.end_ms)
            for c in (analysis.chunks if analysis else ())
        ],
        tokens=[to_token(t) for t in (analysis.tokens if analysis else ())],
        silences=[
            SpanOut(start_ms=s.span.start_ms, end_ms=s.span.end_ms)
            for s in (analysis.silences if analysis else ())
        ],
        suggestions=[to_suggestion(s) for s in (analysis.suggestions if analysis else ())],
        review_marks=[
            ReviewMarkOut(start_ms=m.span.start_ms, end_ms=m.span.end_ms, kind=m.kind)
            for m in (analysis.review_marks if analysis else ())
        ],
    )


def to_edit_state(state: EditState) -> EditStateOut:
    return EditStateOut(
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


def to_export_file(status: ExportFileStatus) -> ExportFileOut:
    return ExportFileOut(
        path=str(status.file.path),
        exported_at=status.file.exported_at,
        job=None if status.job is None else to_job(status.job),
    )


def to_exports(status: ExportStatus) -> ExportsOut:
    return ExportsOut(
        directory=str(status.directory),
        shared_with_other_lectures=status.shared_with_other_lectures,
        premiere_xml=to_export_file(status.premiere),
        mp4=to_export_file(status.mp4),
    )


def to_lecture_detail(
    detail: LectureDetail, settings: ExportSettings, exports: ExportStatus
) -> LectureDetailOut:
    summary = detail.summary
    judgement = detail.judgement
    return LectureDetailOut(
        id=summary.lecture.id,
        title=summary.lecture.title,
        status=summary.status,
        jobs=[to_job(job) for job in summary.jobs],
        recordings=[
            to_recording_detail(
                recording,
                detail.analyses.get(recording.id),
                unreadable=recording.id in detail.unreadable_recording_ids,
            )
            for recording in summary.recordings
        ],
        judged=judgement is not None,
        judged_suggestions=[to_suggestion(s) for s in (judgement.suggestions if judgement else ())],
        dropped_restored_ids=list(judgement.dropped_restored_ids) if judgement else [],
        keep_padding=KeepPaddingOut(
            before_ms=settings.pad_before_ms,
            after_ms=settings.pad_after_ms,
            after_sentence_ms=settings.pad_after_sentence_ms,
        ),
        edit_state=to_edit_state(detail.edit_state),
        exports=to_exports(exports),
    )


def to_keep_padding(padding: KeepPadding) -> KeepPaddingOut:
    return KeepPaddingOut(
        before_ms=padding.before_ms,
        after_ms=padding.after_ms,
        after_sentence_ms=padding.after_sentence_ms,
    )


def to_settings(view: SettingsView) -> SettingsOut:
    return SettingsOut(
        keep_padding=to_keep_padding(view.keep_padding),
        default_keep_padding=to_keep_padding(view.default_keep_padding),
        customized=view.customized,
    )


def to_peaks(peaks: Peaks) -> PeaksOut:
    return PeaksOut(per_second=peaks.per_second, values=list(peaks.values))
