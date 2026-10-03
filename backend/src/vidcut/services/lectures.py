"""レクチャーをまとめる・並べ替える・解除する・解析し直す（US-11。Design Doc 3-5-2）。"""

import logging
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

from vidcut.domain.models import EditState, Job, JobKind, Lecture, ManualCut
from vidcut.domain.titles import normalize_title
from vidcut.pipeline.analysis_result import load_analysis
from vidcut.pipeline.ports import (
    ArtifactStore,
    Atomic,
    EditStateRepository,
    InvalidInputError,
    JobQueue,
    JudgementRepository,
    LectureRepository,
    NotFoundError,
    RecordingRepository,
)
from vidcut.services.imports import FALLBACK_TITLE
from vidcut.services.job_requests import find_queued

JudgeRequester = Callable[[str], object]
"""録画ファイルの id を受け取り、それが属するレクチャーの判定を（解析がそろっていれば）積む。"""

_logger = logging.getLogger(__name__)


class LectureService:
    def __init__(
        self,
        *,
        lectures: LectureRepository,
        recordings: RecordingRepository,
        edit_states: EditStateRepository,
        judgements: JudgementRepository,
        store: ArtifactStore,
        queue: JobQueue,
        atomic: Atomic,
        request_judge: JudgeRequester,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._lectures = lectures
        self._recordings = recordings
        self._edit_states = edit_states
        self._judgements = judgements
        self._store = store
        self._queue = queue
        self._atomic = atomic
        self._request_judge = request_judge
        self._new_id = new_id

    def merge(self, lecture_ids: Sequence[str], title: str | None = None) -> Lecture:
        """複数のレクチャーを、渡した順に 1 つにまとめる。題名を省くと最初のレクチャーの題名。

        編集状態（手動の削除・戻した候補）は引き継ぐ。判定はレクチャー全体でやり直す。
        元のレクチャーを処理中のジョブは、レクチャーがなくなったことで失敗する。
        """
        if len(lecture_ids) < 2 or len(set(lecture_ids)) != len(lecture_ids):
            raise InvalidInputError("まとめるには、異なるレクチャーを 2 つ以上選んでください")
        sources = [self._get(lecture_id) for lecture_id in lecture_ids]
        merged = Lecture(
            id=self._new_id(),
            title=sources[0].title if title is None else _input_title(title),
            recording_ids=tuple(rid for source in sources for rid in source.recording_ids),
        )
        states = [self._edit_states.get(source.id) for source in sources]
        edits = EditState(
            lecture_id=merged.id,
            version=0,
            restored_suggestion_ids=frozenset().union(*(s.restored_suggestion_ids for s in states)),
            manual_cuts=_unique_cuts(cut for state in states for cut in state.manual_cuts),
        )
        self._replace(remove=lecture_ids, save=[(merged, edits)])
        self._request_judge(merged.recording_ids[0])
        return merged

    def reorder(self, lecture_id: str, recording_ids: Sequence[str]) -> Lecture:
        """録画ファイルの順序を変え、判定をやり直す。順序が同じなら何もしない。"""
        lecture = self._get(lecture_id)
        try:
            reordered = lecture.reordered(tuple(recording_ids))
        except ValueError as e:
            raise InvalidInputError(str(e)) from e
        if reordered == lecture:
            return lecture
        self._lectures.save(reordered)
        self._request_judge(reordered.recording_ids[0])
        return reordered

    def split(self, lecture_id: str) -> tuple[Lecture, ...]:
        """まとめたレクチャーを、録画ファイルごとのレクチャーに戻す（題名はファイル名から）。

        編集状態は録画ファイルごとに分ける。どの録画ファイルのものか分からない戻した候補は捨てる。
        """
        lecture = self._get(lecture_id)
        if len(lecture.recording_ids) < 2:
            raise InvalidInputError(f"まとめたレクチャーではありません: {lecture.title}")
        state = self._edit_states.get(lecture_id)
        owners = self._suggestion_owners(lecture) if state.restored_suggestion_ids else {}
        parts: list[tuple[Lecture, EditState]] = []
        for recording_id in lecture.recording_ids:
            part = Lecture(
                id=self._new_id(),
                title=self._file_title(recording_id),
                recording_ids=(recording_id,),
            )
            edits = EditState(
                lecture_id=part.id,
                version=0,
                restored_suggestion_ids=frozenset(
                    sid for sid in state.restored_suggestion_ids if owners.get(sid) == recording_id
                ),
                manual_cuts=tuple(c for c in state.manual_cuts if c.recording_id == recording_id),
            )
            parts.append((part, edits))
        self._replace(remove=[lecture_id], save=parts)
        for part, _ in parts:
            self._request_judge(part.recording_ids[0])
        return tuple(part for part, _ in parts)

    def reanalyze(self, lecture_id: str) -> tuple[Job, ...]:
        """レクチャーの録画ファイルの解析ジョブを積む（解析ロジックを更新したあとに使う）。

        同じ録画ファイルの解析が待機中なら、積まずにそのジョブを返す。
        生成物のキャッシュがあるので、キーが変わった段からだけ作り直される。
        解析が終わると、取り込みのときと同じく判定が積まれる。
        """
        jobs: list[Job] = []
        for recording_id in self._get(lecture_id).recording_ids:
            job = find_queued(self._queue, JobKind.ANALYZE_RECORDING, recording_id)
            if job is None:
                job = Job(id=self._new_id(), kind=JobKind.ANALYZE_RECORDING, target_id=recording_id)
                self._queue.enqueue(job)
            jobs.append(job)
        return tuple(jobs)

    def _replace(self, *, remove: Sequence[str], save: Sequence[tuple[Lecture, EditState]]) -> None:
        """レクチャーの置き換え・編集状態・待機中のジョブの削除を、まとめて確定する。"""
        with self._atomic():
            self._lectures.replace(remove=remove, save=[lecture for lecture, _ in save])
            for _, edits in save:
                if edits.restored_suggestion_ids or edits.manual_cuts:
                    self._edit_states.save(edits)
            # なくなったレクチャーの判定や書き出しを残すと、実行されたときに必ず失敗する
            self._queue.discard_queued_for(remove)

    def _suggestion_owners(self, lecture: Lecture) -> Mapping[str, str]:
        """削除候補の id → 録画ファイルの id（解析結果の無音・フィラーと、判定結果の言い直し）。"""
        owners: dict[str, str] = {}
        for recording_id in lecture.recording_ids:
            try:
                analysis = load_analysis(self._store, recording_id)
            except ValueError:
                # 壊れた解析結果は解析し直すしかなく、その候補を戻した記録も引き継げない
                _logger.warning(
                    "録画ファイル %s の解析結果を読めないため、戻した候補を引き継げません",
                    recording_id,
                )
                continue
            if analysis is not None:
                owners.update({s.id: recording_id for s in analysis.suggestions})
        judgement = self._judgements.get(lecture.id)
        if judgement is not None:
            owners.update({s.id: s.recording_id for s in judgement.suggestions})
        return owners

    def _file_title(self, recording_id: str) -> str:
        recording = self._recordings.get(recording_id)
        if recording is None:
            raise NotFoundError(f"録画ファイルが登録されていません: {recording_id}")
        return normalize_title(Path(recording.source_path).stem, fallback=FALLBACK_TITLE)

    def _get(self, lecture_id: str) -> Lecture:
        lecture = self._lectures.get(lecture_id)
        if lecture is None:
            raise NotFoundError(f"レクチャーがありません: {lecture_id}")
        return lecture


def _input_title(title: str) -> str:
    try:
        return normalize_title(title)
    except ValueError as e:
        raise InvalidInputError(str(e)) from e


def _unique_cuts(cuts: Iterable[ManualCut]) -> tuple[ManualCut, ...]:
    """id が重なった手動の削除は、先のものを残す（EditState は同じ id を 2 つ持てない）。"""
    by_id: dict[str, ManualCut] = {}
    for cut in cuts:
        by_id.setdefault(cut.id, cut)
    return tuple(by_id.values())
