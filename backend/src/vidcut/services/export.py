"""書き出しのジョブの本体（ジョブ export_premiere / export_mp4。Design Doc 3-4）。"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from vidcut.domain.models import Job, JobKind, JobStatus, Lecture, Recording
from vidcut.pipeline.export import ExportPlan, ExportSettings, mezzanine_frame_count, plan_export
from vidcut.pipeline.mezzanine import make_mezzanine
from vidcut.pipeline.ports import (
    ArtifactStore,
    EditStateRepository,
    ExportStore,
    JobQueue,
    JudgementRepository,
    LectureRepository,
    MediaClip,
    MediaTool,
    NotFoundError,
    ProgressReporter,
    RecordingRepository,
)
from vidcut.pipeline.xmeml import XmemlFile, build_xmeml
from vidcut.services.judge import load_lecture_analyses

STAGE = "export"
PREMIERE_SUFFIX = ".xml"
MP4_SUFFIX = ".mp4"
EXPORT_KINDS = frozenset({JobKind.EXPORT_PREMIERE, JobKind.EXPORT_MP4})
# 進捗のうち、中間素材を待つ（なければ作る）部分が占める割合
_MEZZANINE_SHARE_PREMIERE = 0.95
_MEZZANINE_SHARE_MP4 = 0.5


@dataclass(frozen=True)
class _Prepared:
    """書き出しの入力: レクチャー、計画、計画に出てくる録画ファイルとその中間素材。"""

    lecture: Lecture
    plan: ExportPlan
    recordings: dict[str, Recording]
    mezzanines: dict[str, Path]


class ExportService:
    def __init__(
        self,
        *,
        lectures: LectureRepository,
        recordings: RecordingRepository,
        store: ArtifactStore,
        judgements: JudgementRepository,
        edit_states: EditStateRepository,
        queue: JobQueue,
        media: MediaTool,
        exports: ExportStore,
        settings: ExportSettings,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._lectures = lectures
        self._recordings = recordings
        self._store = store
        self._judgements = judgements
        self._edit_states = edit_states
        self._queue = queue
        self._media = media
        self._exports = exports
        self._settings = settings
        self._new_id = new_id

    def request(self, lecture_id: str, kind: JobKind) -> Job:
        """書き出しのジョブを積む。同じ書き出しが待機中なら積まずに、そのジョブを返す。

        待機中のジョブは実行するときの編集状態を読むので、積み直す必要がない。
        確認と登録は 1 つの操作ではない。重なって二重に積まれても、同じファイルを 2 回書くだけ。
        """
        if kind not in EXPORT_KINDS:
            raise ValueError(f"書き出しのジョブではありません: {kind}")
        if self._lectures.get(lecture_id) is None:
            raise NotFoundError(f"レクチャーがありません: {lecture_id}")
        for stored in self._queue.list_all():
            waiting = stored.job
            if (waiting.kind, waiting.target_id, waiting.status) == (
                kind,
                lecture_id,
                JobStatus.QUEUED,
            ):
                return waiting
        job = Job(id=self._new_id(), kind=kind, target_id=lecture_id)
        self._queue.enqueue(job)
        return job

    def export_premiere(self, lecture_id: str, report: ProgressReporter) -> Path:
        """Premiere XML を書き出し、その場所を返す。中間素材がまだなければ、先に作る。"""
        prepared = self._prepare(lecture_id, report, _MEZZANINE_SHARE_PREMIERE)
        report(STAGE, _MEZZANINE_SHARE_PREMIERE)
        files = {
            rid: XmemlFile(
                name=Path(recording.source_path).name,
                path=prepared.mezzanines[rid],
                duration_frames=mezzanine_frame_count(recording.duration_ms, prepared.plan.fps),
                width=recording.media.width,
                height=recording.media.height,
                audio_rate=recording.media.audio_rate,
            )
            for rid, recording in prepared.recordings.items()
        }
        xml = build_xmeml(prepared.lecture.title, prepared.plan, files)
        path = self._exports.write_text(prepared.lecture.title, PREMIERE_SUFFIX, xml)
        report(STAGE, 1.0)
        return path

    def export_mp4(self, lecture_id: str, report: ProgressReporter) -> Path:
        """カット済みの MP4 を書き出し、その場所を返す。中間素材がまだなければ、先に作る。"""
        prepared = self._prepare(lecture_id, report, _MEZZANINE_SHARE_MP4)
        report(STAGE, _MEZZANINE_SHARE_MP4)
        clips = [
            MediaClip(prepared.mezzanines[clip.recording_id], clip.frames)
            for clip in prepared.plan.clips
        ]
        path = self._exports.path(prepared.lecture.title, MP4_SUFFIX)
        encode_share = 1.0 - _MEZZANINE_SHARE_MP4
        self._media.export_mp4(
            clips,
            path,
            fps=prepared.plan.fps,
            on_progress=lambda f: report(STAGE, _MEZZANINE_SHARE_MP4 + f * encode_share),
        )
        report(STAGE, 1.0)
        return path

    def _prepare(self, lecture_id: str, report: ProgressReporter, share: float) -> _Prepared:
        """残す区間を求め、使う録画ファイルの中間素材をそろえる。progress は 0〜share を使う。"""
        lecture = self._lectures.get(lecture_id)
        if lecture is None:
            raise NotFoundError(f"レクチャーがありません: {lecture_id}")
        recordings = [self._recording(rid) for rid in lecture.recording_ids]
        analyses = load_lecture_analyses(lecture, self._store)
        # 判定がまだ（または失敗）でも、無音とフィラーの削除候補だけで書き出せる
        judgement = self._judgements.get(lecture_id)
        plan = plan_export(
            recordings,
            analyses,
            judgement.suggestions if judgement else (),
            self._edit_states.get(lecture_id),
            self._settings,
        )
        if not plan.clips:
            raise ValueError(f"残す区間がありません（すべて削除されています）: {lecture.title}")
        used_ids = {clip.recording_id for clip in plan.clips}
        used = [recording for recording in recordings if recording.id in used_ids]
        return _Prepared(
            lecture=lecture,
            plan=plan,
            recordings={recording.id: recording for recording in used},
            mezzanines=self._ensure_mezzanines(used, report, share),
        )

    def _ensure_mezzanines(
        self, recordings: Sequence[Recording], report: ProgressReporter, share: float
    ) -> dict[str, Path]:
        """中間素材の完成を待つ。worker は 1 つなので、まだなければこのジョブの中で作る。

        後から来る make_mezzanine のジョブは、できあがった中間素材を見つけてすぐ終わる。
        """
        paths: dict[str, Path] = {}
        for index, recording in enumerate(recordings):

            def scaled(stage: str | None, fraction: float, done: int = index) -> None:
                report(stage, (done + fraction) / len(recordings) * share)

            paths[recording.id] = make_mezzanine(recording, self._media, self._store, scaled)
        return paths

    def _recording(self, recording_id: str) -> Recording:
        recording = self._recordings.get(recording_id)
        if recording is None:
            raise NotFoundError(f"録画ファイルが登録されていません: {recording_id}")
        return recording
