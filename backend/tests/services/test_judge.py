import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from tests.pipeline.fakes import DirectoryStore, make_recording
from tests.pipeline.judge_fakes import FakeModel, delete_output, make_analysis
from vidcut.adapters.sqlite.database import open_database, transaction
from vidcut.adapters.sqlite.edit_states import SqliteEditStateRepository
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.adapters.sqlite.judgements import SqliteJudgementRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, EditState, JobKind, JobStatus, Lecture
from vidcut.pipeline.analysis_result import save_analysis
from vidcut.pipeline.judge import JudgeOutputError, JudgeSettings
from vidcut.pipeline.ports import (
    EditStateRepository,
    ExternalToolError,
    Judgement,
    JudgementRepository,
    LoginRequiredError,
    NotFoundError,
    VersionConflictError,
)
from vidcut.services.judge import JudgeRequests, JudgeService


@dataclass
class Env:
    conn: sqlite3.Connection
    store: DirectoryStore
    lectures: SqliteLectureRepository
    edit_states: SqliteEditStateRepository
    judgements: SqliteJudgementRepository
    queue: SqliteJobQueue

    def service(
        self,
        outputs: Sequence[str | Exception] = (),
        settings: JudgeSettings | None = None,
        edit_states: EditStateRepository | None = None,
        judgements: JudgementRepository | None = None,
    ) -> tuple[JudgeService, FakeModel]:
        model = FakeModel(outputs)
        ids = iter(f"job{i}" for i in range(100))
        service = JudgeService(
            lectures=self.lectures,
            store=self.store,
            judgements=judgements or self.judgements,
            edit_states=edit_states or self.edit_states,
            atomic=lambda: transaction(self.conn),
            queue=self.queue,
            model=model,
            settings=settings or JudgeSettings(),
            prompt="指示文\n",
            new_id=lambda: next(ids),
        )
        return service, model

    def analyzed(self, rid: str, texts: Sequence[str]) -> None:
        save_analysis(self.store, make_analysis(rid, texts))


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    conn = open_database(tmp_path / "db.sqlite3")
    recordings = SqliteRecordingRepository(conn)
    for rid in ("r1", "r2"):
        recordings.add(make_recording(tmp_path / f"{rid}.mov", rid))
    lectures = SqliteLectureRepository(conn)
    lectures.save(Lecture(id="l1", title="S05-12", recording_ids=("r1", "r2")))
    yield Env(
        conn=conn,
        store=DirectoryStore(tmp_path / "ws"),
        lectures=lectures,
        edit_states=SqliteEditStateRepository(conn),
        judgements=SqliteJudgementRepository(conn),
        queue=SqliteJobQueue(conn),
    )
    conn.close()


def ignore(stage: str | None, progress: float) -> None:
    pass


RETAKE_ACROSS_FILES = delete_output(
    {"id": 1, "kind": "retake", "reason": "次のファイルで言い直している", "superseded_by": 2},
)


class TestJudge:
    def test_judges_chunks_of_all_recordings_in_lecture_order(self, env: Env) -> None:
        env.analyzed("r1", ("前半です", "クライアントから"))
        env.analyzed("r2", ("クライアントから送られる値", "以上です"))
        service, model = env.service([RETAKE_ACROSS_FILES])
        reported: list[tuple[str | None, float]] = []
        judgement = service.judge("l1", lambda stage, progress: reported.append((stage, progress)))
        (suggestion,) = judgement.suggestions
        assert suggestion.id == "r1-c0001-judged"
        assert suggestion.kind is CutKind.RETAKE
        assert suggestion.superseded_by == "r2-c0000"
        assert env.judgements.get("l1") == judgement
        (prompt,) = model.prompts
        assert prompt.startswith("指示文\n0\t")
        assert prompt.index("クライアントから") < prompt.index("録画ファイルが切り替わる")
        assert reported[0] == ("judge", 0.0)
        assert reported[-1] == ("judge", 1.0)

    def test_follows_lecture_order_not_registration_order(self, env: Env) -> None:
        env.analyzed("r1", ("一本目",))
        env.analyzed("r2", ("二本目",))
        env.lectures.save(Lecture(id="l1", title="S05-12", recording_ids=("r2", "r1")))
        service, model = env.service(['{"delete": []}'])
        service.judge("l1", ignore)
        assert model.prompts[0].index("二本目") < model.prompts[0].index("一本目")

    def test_skips_model_when_input_is_unchanged(self, env: Env) -> None:
        env.analyzed("r1", ("a", "b"))
        env.analyzed("r2", ("c",))
        first, _ = env.service([RETAKE_ACROSS_FILES])
        judgement = first.judge("l1", ignore)
        second, model = env.service([])
        assert second.judge("l1", ignore) == judgement
        assert model.prompts == []

    def test_judges_again_when_transcript_changed(self, env: Env) -> None:
        env.analyzed("r1", ("a", "b"))
        env.analyzed("r2", ("c",))
        env.service([RETAKE_ACROSS_FILES])[0].judge("l1", ignore)
        env.analyzed("r2", ("c", "d"))
        service, model = env.service(['{"delete": []}'])
        assert service.judge("l1", ignore).suggestions == ()
        assert len(model.prompts) == 1

    def test_lecture_without_speech_gets_empty_judgement(self, env: Env) -> None:
        env.analyzed("r1", ())
        env.analyzed("r2", ("",))
        service, model = env.service([])
        assert service.judge("l1", ignore).suggestions == ()
        assert model.prompts == []
        assert env.judgements.get("l1") is not None

    def test_unknown_lecture(self, env: Env) -> None:
        service, _ = env.service([])
        with pytest.raises(NotFoundError, match="レクチャー"):
            service.judge("nope", ignore)

    def test_recording_not_analyzed_yet(self, env: Env) -> None:
        env.analyzed("r1", ("a",))
        service, model = env.service([])
        with pytest.raises(NotFoundError, match="解析"):
            service.judge("l1", ignore)
        assert model.prompts == []

    @pytest.mark.parametrize(
        "error", [LoginRequiredError("`/login` が必要です"), ExternalToolError("時間内に…")]
    )
    def test_model_failure_keeps_previous_result(self, env: Env, error: Exception) -> None:
        env.analyzed("r1", ("a", "b"))
        env.analyzed("r2", ("c",))
        previous = env.service([RETAKE_ACROSS_FILES])[0].judge("l1", ignore)
        env.analyzed("r2", ("c", "d"))
        service, model = env.service([error])
        with pytest.raises(type(error)):
            service.judge("l1", ignore)
        assert len(model.prompts) == 1  # 外部ツールの失敗は再試行しない
        assert env.judgements.get("l1") == previous

    def test_unreadable_output_twice_fails_without_saving(self, env: Env) -> None:
        env.analyzed("r1", ("a",))
        env.analyzed("r2", ("c",))
        service, _ = env.service(["???", "???"])
        with pytest.raises(JudgeOutputError):
            service.judge("l1", ignore)
        assert env.judgements.get("l1") is None

    def test_long_lecture_is_judged_in_windows(self, env: Env) -> None:
        env.analyzed("r1", tuple(f"a{i}" for i in range(8)))
        env.analyzed("r2", tuple(f"b{i}" for i in range(8)))
        first = delete_output({"id": 2, "kind": "noise", "reason": "独り言"})
        second = delete_output({"id": 15, "kind": "misspeak", "reason": "途切れ"})
        service, model = env.service([first, second], JudgeSettings(max_chunks=10, overlap=4))
        judgement = service.judge("l1", ignore)
        assert [s.id for s in judgement.suggestions] == ["r1-c0002-judged", "r2-c0007-judged"]
        assert len(model.prompts) == 2


class TestCarryOverRestorations:
    def judged_twice(self, env: Env, second_output: str) -> None:
        env.analyzed("r1", ("a", "b"))
        env.analyzed("r2", ("c",))
        env.service([RETAKE_ACROSS_FILES])[0].judge("l1", ignore)
        state = EditState(lecture_id="l1", version=0)
        env.edit_states.save(state.restore("r1-c0001-judged").restore("r1-silence-0000"))
        env.analyzed("r2", ("c", "d"))  # 入力が変わり、判定をやり直す
        env.service([second_output])[0].judge("l1", ignore)

    def test_keeps_restorations_that_still_exist(self, env: Env) -> None:
        self.judged_twice(env, RETAKE_ACROSS_FILES)
        state = env.edit_states.get("l1")
        assert state.restored_suggestion_ids == {"r1-c0001-judged", "r1-silence-0000"}
        assert state.version == 1  # 変わらなければ保存し直さない
        judgement = env.judgements.get("l1")
        assert judgement is not None
        assert judgement.dropped_restored_ids == ()

    def test_drops_restoration_whose_suggestion_is_gone(self, env: Env) -> None:
        self.judged_twice(env, '{"delete": []}')
        state = env.edit_states.get("l1")
        assert state.restored_suggestion_ids == {"r1-silence-0000"}
        assert state.version == 2
        judgement = env.judgements.get("l1")
        assert judgement is not None
        assert judgement.dropped_restored_ids == ("r1-c0001-judged",)

    def test_moves_restoration_to_matching_suggestion_after_reanalysis(self, env: Env) -> None:
        env.analyzed("r1", ("a", "b"))
        env.analyzed("r2", ("c",))
        env.service([RETAKE_ACROSS_FILES])[0].judge("l1", ignore)
        env.edit_states.save(EditState(lecture_id="l1", version=0).restore("r1-c0001-judged"))
        # 解析し直してチャンクの分かれ方が変わり、同じ発話が 3 番目のチャンク（id は別）になった
        reanalyzed = make_analysis("r1", ("a", "", "b"))
        moved = replace(reanalyzed.chunks[2], span=Interval(2_050, 3_100))
        save_analysis(env.store, replace(reanalyzed, chunks=(*reanalyzed.chunks[:2], moved)))
        output = delete_output({"id": 2, "kind": "retake", "reason": "言い直し"})
        judgement = env.service([output])[0].judge("l1", ignore)
        assert [s.id for s in judgement.suggestions] == ["r1-c0002-judged"]
        assert env.edit_states.get("l1").restored_suggestion_ids == {"r1-c0002-judged"}
        assert judgement.dropped_restored_ids == ()

    def test_retries_when_edit_state_was_saved_concurrently(self, env: Env) -> None:
        env.analyzed("r1", ("a", "b"))
        env.analyzed("r2", ("c",))
        env.service([RETAKE_ACROSS_FILES])[0].judge("l1", ignore)
        env.edit_states.save(EditState(lecture_id="l1", version=0).restore("r1-c0001-judged"))
        env.analyzed("r2", ("c", "d"))
        conflicts = _ConflictingOnce(env.edit_states)
        service, _ = env.service(['{"delete": []}'], edit_states=conflicts)
        service.judge("l1", ignore)
        assert conflicts.attempts == 2
        assert env.edit_states.get("l1").restored_suggestion_ids == frozenset()

    def test_gives_up_when_edit_state_keeps_changing(self, env: Env) -> None:
        env.analyzed("r1", ("a", "b"))
        env.analyzed("r2", ("c",))
        env.service([RETAKE_ACROSS_FILES])[0].judge("l1", ignore)
        env.edit_states.save(EditState(lecture_id="l1", version=0).restore("r1-c0001-judged"))
        env.analyzed("r2", ("c", "d"))
        conflicts = _ConflictingOnce(env.edit_states, times=99)
        service, _ = env.service(['{"delete": []}'], edit_states=conflicts)
        with pytest.raises(VersionConflictError):
            service.judge("l1", ignore)
        judgement = env.judgements.get("l1")
        assert judgement is not None
        assert [s.id for s in judgement.suggestions] == ["r1-c0001-judged"]  # 前回のまま

    def test_edit_state_is_not_changed_when_the_judgement_cannot_be_saved(self, env: Env) -> None:
        # 編集状態だけが新しくなると、画面は「戻した候補」を古い判定結果と突き合わせてしまう
        env.analyzed("r1", ("a", "b"))
        env.analyzed("r2", ("c",))
        env.service([RETAKE_ACROSS_FILES])[0].judge("l1", ignore)
        env.edit_states.save(EditState(lecture_id="l1", version=0).restore("r1-c0001-judged"))
        env.analyzed("r2", ("c", "d"))
        service, _ = env.service(['{"delete": []}'], judgements=_UnwritableJudgements(env))
        with pytest.raises(sqlite3.OperationalError):
            service.judge("l1", ignore)
        state = env.edit_states.get("l1")
        assert (state.version, state.restored_suggestion_ids) == (1, {"r1-c0001-judged"})


class _ConflictingOnce:
    """最初の times 回の保存を、別の画面が先に保存したことにして失敗させる。"""

    def __init__(self, inner: SqliteEditStateRepository, times: int = 1) -> None:
        self._inner = inner
        self._times = times
        self.attempts = 0

    def get(self, lecture_id: str) -> EditState:
        return self._inner.get(lecture_id)

    def save(self, state: EditState) -> EditState:
        self.attempts += 1
        if self.attempts <= self._times:
            raise VersionConflictError("別の画面で更新されています")
        return self._inner.save(state)


class _UnwritableJudgements:
    """判定結果の保存だけが失敗する（ディスクがいっぱい、など）。"""

    def __init__(self, env: Env) -> None:
        self._inner = env.judgements

    def get(self, lecture_id: str) -> Judgement | None:
        return self._inner.get(lecture_id)

    def save(self, judgement: Judgement) -> None:
        raise sqlite3.OperationalError("database or disk is full")


class TestJudgeRequests:
    def test_enqueues_without_a_language_model(self, env: Env) -> None:
        # API サーバーは判定を積むだけで、言語モデルを持たない
        env.analyzed("r1", ("a",))
        env.analyzed("r2", ("b",))
        requests = JudgeRequests(
            lectures=env.lectures, store=env.store, queue=env.queue, new_id=lambda: "job-api"
        )
        job = requests.for_recording("r2")
        assert job is not None
        assert (job.id, job.kind, job.target_id) == ("job-api", JobKind.JUDGE_LECTURE, "l1")
        assert requests.for_recording("r1") is None  # 待機中なら積まない


class TestRequestForRecording:
    def judge_jobs(self, env: Env) -> list[tuple[str, JobStatus]]:
        return [
            (s.job.target_id, s.job.status)
            for s in env.queue.list_all()
            if s.job.kind is JobKind.JUDGE_LECTURE
        ]

    def test_enqueues_judge_when_all_recordings_are_analyzed(self, env: Env) -> None:
        env.analyzed("r1", ("a",))
        env.analyzed("r2", ("b",))
        service, _ = env.service()
        job = service.request_for_recording("r2")
        assert job is not None
        assert (job.kind, job.target_id) == (JobKind.JUDGE_LECTURE, "l1")
        assert self.judge_jobs(env) == [("l1", JobStatus.QUEUED)]

    def test_waits_until_every_recording_is_analyzed(self, env: Env) -> None:
        env.analyzed("r1", ("a",))
        service, _ = env.service()
        assert service.request_for_recording("r1") is None
        assert self.judge_jobs(env) == []

    def test_does_not_enqueue_twice_while_one_is_waiting(self, env: Env) -> None:
        env.analyzed("r1", ("a",))
        env.analyzed("r2", ("b",))
        service, _ = env.service()
        service.request_for_recording("r1")
        assert service.request_for_recording("r2") is None
        assert self.judge_jobs(env) == [("l1", JobStatus.QUEUED)]

    def test_enqueues_again_after_previous_job_started(self, env: Env) -> None:
        env.analyzed("r1", ("a",))
        env.analyzed("r2", ("b",))
        service, _ = env.service()
        service.request_for_recording("r1")
        env.queue.claim_next()  # 実行中の判定は、いまの解析結果を読んでいないかもしれない
        assert service.request_for_recording("r2") is not None
        assert self.judge_jobs(env) == [("l1", JobStatus.RUNNING), ("l1", JobStatus.QUEUED)]

    def test_recording_without_lecture(self, env: Env) -> None:
        env.lectures.delete("l1")
        service, _ = env.service()
        assert service.request_for_recording("r1") is None

    def test_broken_analysis_is_left_for_the_judge_job_to_report(self, env: Env) -> None:
        env.analyzed("r1", ("a",))
        env.store.path("r2", "analysis.json").write_text("{broken")
        service, _ = env.service()
        assert service.request_for_recording("r1") is not None
        with pytest.raises(ValueError):
            service.judge("l1", ignore)
