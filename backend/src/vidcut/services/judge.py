"""言い直しの判定のジョブの本体（ジョブ judge_lecture。Design Doc 3-3）。"""

import logging
import uuid
from collections.abc import Callable, Sequence

from vidcut.domain.models import CutSuggestion, Job, JobKind, Lecture
from vidcut.domain.overrides import carry_over_restorations
from vidcut.pipeline.analysis_result import Analysis, load_analysis
from vidcut.pipeline.judge import (
    JudgeEntry,
    JudgeSettings,
    build_entries,
    input_key,
    judge_entries,
    load_prompt,
    to_suggestions,
)
from vidcut.pipeline.ports import (
    ArtifactStore,
    Atomic,
    EditStateRepository,
    JobQueue,
    Judgement,
    JudgementRepository,
    LanguageModel,
    LectureRepository,
    NotFoundError,
    ProgressReporter,
    VersionConflictError,
)
from vidcut.services.job_requests import find_queued

STAGE = "judge"
_SAVE_ATTEMPTS = 3
_MODEL_SHARE = 0.95  # 進捗のうち、言語モデルの応答待ちが占める割合

_logger = logging.getLogger(__name__)


def load_lecture_analyses(lecture: Lecture, store: ArtifactStore) -> tuple[Analysis, ...]:
    """レクチャーの録画ファイルの解析結果を順序どおりに読む。未解析のものがあれば NotFoundError。"""
    analyses: list[Analysis] = []
    for recording_id in lecture.recording_ids:
        analysis = load_analysis(store, recording_id)
        if analysis is None:
            raise NotFoundError(f"録画ファイルの解析が終わっていません: {recording_id}")
        analyses.append(analysis)
    return tuple(analyses)


class JudgeRequests:
    """判定ジョブの登録。API サーバーは言語モデルを持たないので、JudgeService と分ける。"""

    def __init__(
        self,
        *,
        lectures: LectureRepository,
        store: ArtifactStore,
        queue: JobQueue,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._lectures = lectures
        self._store = store
        self._queue = queue
        self._new_id = new_id

    def for_recording(self, recording_id: str) -> Job | None:
        """録画ファイルが属するレクチャーの判定を積む。全ファイルが解析済みのときだけ積む。

        解析が終わったときと、レクチャーをまとめる・並べ替える・解除したときに呼ぶ。
        同じレクチャーの判定が既に待機中なら積まない（そのジョブがいまの解析結果を読む）。
        重なって二重に積まれても、2 本目は入力が同じなので言語モデルを呼ばずに終わる。
        """
        lecture = self._lectures.find_by_recording(recording_id)
        if lecture is None or not all(self._is_analyzed(rid) for rid in lecture.recording_ids):
            return None
        if find_queued(self._queue, JobKind.JUDGE_LECTURE, lecture.id) is not None:
            return None
        job = Job(id=self._new_id(), kind=JobKind.JUDGE_LECTURE, target_id=lecture.id)
        self._queue.enqueue(job)
        return job

    def _is_analyzed(self, recording_id: str) -> bool:
        try:
            return load_analysis(self._store, recording_id) is not None
        except ValueError:
            # 壊れた解析結果は、判定ジョブが失敗として表に出す
            return True


class JudgeService:
    def __init__(
        self,
        *,
        lectures: LectureRepository,
        store: ArtifactStore,
        judgements: JudgementRepository,
        edit_states: EditStateRepository,
        atomic: Atomic,
        queue: JobQueue,
        model: LanguageModel,
        settings: JudgeSettings,
        prompt: str | None = None,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._lectures = lectures
        self._store = store
        self._judgements = judgements
        self._edit_states = edit_states
        self._atomic = atomic
        self._model = model
        self._settings = settings
        self._prompt = load_prompt() if prompt is None else prompt
        self._requests = JudgeRequests(lectures=lectures, store=store, queue=queue, new_id=new_id)

    def judge(self, lecture_id: str, report: ProgressReporter) -> Judgement:
        """レクチャー全体の発話チャンクを判定し、結果を保存する。

        入力（指示文とチャンク）が前回と同じなら、言語モデルを呼ばずに前回の結果を返す。
        失敗したときは前回の結果を残す（無音とフィラーの削除候補は解析結果にあり、影響を受けない）。
        """
        lecture = self._lectures.get(lecture_id)
        if lecture is None:
            raise NotFoundError(f"レクチャーがありません: {lecture_id}")
        analyses = load_lecture_analyses(lecture, self._store)
        entries = build_entries(analyses)
        key = input_key(self._prompt, entries, self._settings)
        previous = self._judgements.get(lecture_id)
        if previous is not None and previous.input_key == key:
            report(STAGE, 1.0)
            return previous
        report(STAGE, 0.0)
        suggestions = self._suggest(entries, report)
        judgement = self._save(lecture_id, key, analyses, previous, suggestions)
        report(STAGE, 1.0)
        return judgement

    def request_for_recording(self, recording_id: str) -> Job | None:
        """解析が終わった録画ファイルのレクチャーの判定を積む（JudgeRequests.for_recording）。"""
        return self._requests.for_recording(recording_id)

    def _suggest(
        self, entries: Sequence[JudgeEntry], report: ProgressReporter
    ) -> tuple[CutSuggestion, ...]:
        decisions = judge_entries(
            self._model,
            entries,
            self._settings,
            prompt=self._prompt,
            on_progress=lambda fraction: report(STAGE, fraction * _MODEL_SHARE),
        )
        return to_suggestions(entries, decisions)

    def _save(
        self,
        lecture_id: str,
        key: str,
        analyses: Sequence[Analysis],
        previous: Judgement | None,
        suggestions: tuple[CutSuggestion, ...],
    ) -> Judgement:
        """戻した削除候補を新しい判定へ引き継ぎ（Design Doc 4 章）、編集状態と判定結果を保存する。

        2 つはまとめて確定する。編集状態だけが先に新しくなると、画面は戻した候補の id を
        古い判定結果と突き合わせ、戻したはずの候補を削除として表示してしまう。
        引き継げなかった id は判定結果に残す（画面の通知用）。
        """
        unchanged = tuple(s for analysis in analyses for s in analysis.suggestions)
        old = (*unchanged, *(previous.suggestions if previous else ()))
        new = (*unchanged, *suggestions)
        for _ in range(_SAVE_ATTEMPTS):
            state = self._edit_states.get(lecture_id)
            result = carry_over_restorations(state, old, new)
            judgement = Judgement(lecture_id, key, suggestions, result.dropped_suggestion_ids)
            try:
                with self._atomic():
                    if result.state != state:
                        self._edit_states.save(result.state)
                    self._judgements.save(judgement)
            except VersionConflictError:
                continue  # 画面が先に保存した。読み直してやり直す
            if result.dropped_suggestion_ids:
                _logger.info(
                    "レクチャー %s: 戻した削除候補 %d 件を引き継げませんでした",
                    lecture_id,
                    len(result.dropped_suggestion_ids),
                )
            return judgement
        raise VersionConflictError(
            f"編集状態が更新され続けているため、判定結果を反映できませんでした: {lecture_id}"
        )
