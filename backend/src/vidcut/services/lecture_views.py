"""レクチャーの一覧と、編集画面に必要なもの一式（Design Doc 3-5 の GET /api/lectures）。"""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from vidcut.domain.models import EditState, Job, JobKind, JobStatus, Lecture, Recording
from vidcut.pipeline.analysis_result import Analysis, load_analysis
from vidcut.pipeline.ports import (
    ArtifactStore,
    EditStateRepository,
    JobQueue,
    Judgement,
    JudgementRepository,
    LectureRepository,
    NotFoundError,
    RecordingRepository,
    StoredJob,
)

_logger = logging.getLogger(__name__)


class LectureStatus(StrEnum):
    """素材一覧に出す状態（Design Doc 3-6）。"""

    QUEUED = "queued"  # 待機中
    ANALYZING = "analyzing"  # 解析中
    JUDGING = "judging"  # 判定中
    READY = "ready"  # 編集待ち
    FAILED = "failed"  # 失敗


@dataclass(frozen=True)
class LectureSummary:
    """jobs は状態の根拠: 各録画ファイルの解析と、レクチャーの判定の、それぞれ最新のジョブ。"""

    lecture: Lecture
    recordings: tuple[Recording, ...]  # レクチャー内の順
    status: LectureStatus
    jobs: tuple[Job, ...]


@dataclass(frozen=True)
class LectureDetail:
    """編集画面に必要なもの一式。

    analyses は解析が済んだ録画ファイルの分だけ（レクチャー内の順）。
    judgement は判定がまだなら None。
    unreadable_recording_ids は、解析結果が読めない（古い形・壊れている）録画ファイル。
    解析し直せば直る。
    """

    summary: LectureSummary
    analyses: Mapping[str, Analysis]
    judgement: Judgement | None
    edit_state: EditState
    unreadable_recording_ids: tuple[str, ...]


def lecture_status(jobs: Iterable[Job]) -> LectureStatus:
    """最新のジョブ（解析・判定）から状態を決める。

    動いているものがあるうちはその状態を出し、失敗はすべて止まってから出す。
    ジョブが 1 つもない、またはすべて成功していれば編集待ち。
    判定が失敗しても、無音とフィラーの削除候補で編集はできる（画面は失敗を示したうえで開ける）。
    """
    states = {(job.kind, job.status) for job in jobs}
    if (JobKind.ANALYZE_RECORDING, JobStatus.RUNNING) in states:
        return LectureStatus.ANALYZING
    if (JobKind.JUDGE_LECTURE, JobStatus.RUNNING) in states:
        return LectureStatus.JUDGING
    statuses = {status for _, status in states}
    if JobStatus.QUEUED in statuses:
        return LectureStatus.QUEUED
    if JobStatus.FAILED in statuses:
        return LectureStatus.FAILED
    return LectureStatus.READY


class LectureQuery:
    def __init__(
        self,
        *,
        lectures: LectureRepository,
        recordings: RecordingRepository,
        edit_states: EditStateRepository,
        judgements: JudgementRepository,
        store: ArtifactStore,
        queue: JobQueue,
    ) -> None:
        self._lectures = lectures
        self._recordings = recordings
        self._edit_states = edit_states
        self._judgements = judgements
        self._store = store
        self._queue = queue

    def summaries(self) -> tuple[LectureSummary, ...]:
        """すべてのレクチャー（登録順）。解析結果のファイルは読まない（1 秒ごとに呼ばれる）。"""
        recordings = {recording.id: recording for recording in self._recordings.list_all()}
        stored_jobs = self._queue.list_all()
        return tuple(
            _summarize(lecture, recordings, stored_jobs) for lecture in self._lectures.list_all()
        )

    def detail(self, lecture_id: str) -> LectureDetail:
        lecture = self._lectures.get(lecture_id)
        if lecture is None:
            raise NotFoundError(f"レクチャーがありません: {lecture_id}")
        recordings = {rid: self._recordings.get(rid) for rid in lecture.recording_ids}
        summary = _summarize(lecture, recordings, self._queue.list_all())
        analyses: dict[str, Analysis] = {}
        unreadable: list[str] = []
        for recording_id in lecture.recording_ids:
            try:
                analysis = load_analysis(self._store, recording_id)
            except ValueError:
                # 画面を開けなくすると解析し直すこともできないので、読めないことを伝えて先へ進む
                _logger.warning(
                    "録画ファイル %s の解析結果を読めません", recording_id, exc_info=True
                )
                unreadable.append(recording_id)
                continue
            if analysis is not None:
                analyses[recording_id] = analysis
        return LectureDetail(
            summary=summary,
            analyses=analyses,
            judgement=self._judgements.get(lecture_id),
            edit_state=self._edit_states.get(lecture_id),
            unreadable_recording_ids=tuple(unreadable),
        )


def _summarize(
    lecture: Lecture,
    recordings: Mapping[str, Recording | None],
    stored_jobs: Sequence[StoredJob],
) -> LectureSummary:
    jobs = _latest_jobs(lecture, stored_jobs)
    return LectureSummary(
        lecture=lecture,
        recordings=tuple(_require(recordings.get(rid), rid) for rid in lecture.recording_ids),
        status=lecture_status(jobs),
        jobs=jobs,
    )


def _require(recording: Recording | None, recording_id: str) -> Recording:
    if recording is None:
        raise NotFoundError(f"録画ファイルが登録されていません: {recording_id}")
    return recording


def _latest_jobs(lecture: Lecture, stored_jobs: Sequence[StoredJob]) -> tuple[Job, ...]:
    """各録画ファイルの解析と、レクチャーの判定の、最新のジョブ（録画ファイルの順、判定は最後）。

    中間素材と書き出しのジョブは、編集できるかどうかに関係しないので含めない。
    """
    targets = [(JobKind.ANALYZE_RECORDING, rid) for rid in lecture.recording_ids]
    targets.append((JobKind.JUDGE_LECTURE, lecture.id))
    latest: dict[tuple[JobKind, str], Job] = {}
    for stored in stored_jobs:  # 登録順なので、後のものが残る
        latest[(stored.job.kind, stored.job.target_id)] = stored.job
    return tuple(latest[target] for target in targets if target in latest)
