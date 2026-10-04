import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from tests.pipeline.fakes import (
    DirectoryStore,
    FakeAligner,
    FakeMediaTool,
    FakeTranscriber,
    FakeVad,
    make_recording,
)
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.edit_states import SqliteEditStateRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion, EditState, Lecture
from vidcut.pipeline.analysis import AnalysisSettings, AnalysisTools, load_analysis
from vidcut.pipeline.analysis_result import Analysis, save_analysis
from vidcut.pipeline.ports import NotFoundError, VersionConflictError
from vidcut.services.analysis import AnalysisService


@dataclass
class Env:
    service: AnalysisService
    edit_states: SqliteEditStateRepository  # テストが直接読み書きする（衝突しない）
    conn: sqlite3.Connection
    colliding: "CollidingEditStates"


class CollidingEditStates:
    """保存の最初の何回かを、画面の保存と重なったことにする（版の食い違い）。"""

    def __init__(self, inner: SqliteEditStateRepository, conflicts: int) -> None:
        self._inner = inner
        self.remaining = 0
        self._conflicts = conflicts

    def arm(self) -> None:
        self.remaining = self._conflicts

    def get(self, lecture_id: str) -> EditState:
        return self._inner.get(lecture_id)

    def save(self, state: EditState) -> EditState:
        if self.remaining > 0:
            self.remaining -= 1
            raise VersionConflictError("画面の保存と重なった")
        return self._inner.save(state)


def build_env(
    tmp_path: Path, *, recording_ids: tuple[str, ...] = ("r1",), conflicts: int = 0
) -> Env:
    conn: sqlite3.Connection = open_database(tmp_path / "db.sqlite3")
    recordings = SqliteRecordingRepository(conn)
    for rid in recording_ids:
        source = tmp_path / f"{rid}.mov"
        source.write_bytes(b"mov")
        recordings.add(make_recording(source, rid))
    lectures = SqliteLectureRepository(conn)
    lectures.save(Lecture(id="l1", title="a", recording_ids=recording_ids))
    edit_states = SqliteEditStateRepository(conn)
    colliding = CollidingEditStates(edit_states, conflicts)
    tools = AnalysisTools(
        media=FakeMediaTool(),
        vad=FakeVad(),
        transcriber=FakeTranscriber(),
        aligner=FakeAligner(),
        store=DirectoryStore(tmp_path / "ws"),
    )
    service = AnalysisService(
        recordings, tools, AnalysisSettings(), lectures=lectures, edit_states=colliding
    )
    return Env(service, edit_states, conn, colliding)


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    built = build_env(tmp_path)
    yield built
    built.conn.close()


@pytest.fixture
def service(env: Env) -> AnalysisService:
    return env.service


def test_analyze_saves_result(service: AnalysisService) -> None:
    analysis = service.analyze("r1", lambda s, p: None)
    assert load_analysis(service.store, "r1") == analysis


def test_make_mezzanine(service: AnalysisService) -> None:
    path = service.make_mezzanine("r1", lambda s, p: None)
    assert path.read_bytes() == b"mezzanine"


def test_unknown_recording(service: AnalysisService) -> None:
    with pytest.raises(NotFoundError):
        service.analyze("nope", lambda s, p: None)
    with pytest.raises(NotFoundError):
        service.make_mezzanine("nope", lambda s, p: None)


class TestReanalysis:
    """解析し直したとき、戻していた無音・フィラーを、新しい候補へ引き継ぐ。"""

    def _filler_id(self, analysis: Analysis) -> str:
        (filler,) = [s for s in analysis.suggestions if s.kind is CutKind.FILLER]
        return filler.id

    def _save_as_old(self, env: Env, analysis: Analysis, fillers: list[CutSuggestion]) -> None:
        """前の解析結果として、フィラーの候補だけを差し替えて保存する。"""
        others = tuple(s for s in analysis.suggestions if s.kind is not CutKind.FILLER)
        save_analysis(env.service.store, replace(analysis, suggestions=(*others, *fillers)))

    def test_restored_filler_follows_the_new_candidate(self, env: Env) -> None:
        analysis = env.service.analyze("r1", lambda s, p: None)
        # 前の規則では、同じフィラーが別の id と短い区間だった
        old = CutSuggestion("r1-c0000-filler-7", "r1", Interval(1_000, 1_300), CutKind.FILLER, "")
        self._save_as_old(env, analysis, [old])
        saved = env.edit_states.save(EditState("l1", 0).restore(old.id).restore("r1-c0001-judged"))

        env.service.analyze("r1", lambda s, p: None)

        state = env.edit_states.get("l1")
        assert state.restored_suggestion_ids == frozenset(
            {self._filler_id(analysis), "r1-c0001-judged"}
        )
        assert state.version == saved.version + 1

    def test_restoration_does_not_move_to_another_filler_with_the_same_id(self, env: Env) -> None:
        analysis = env.service.analyze("r1", lambda s, p: None)
        # 前の filler-0 は別の場所のフィラーで、新しい解析では候補でなくなった
        gone = CutSuggestion(
            self._filler_id(analysis), "r1", Interval(6_000, 6_200), CutKind.FILLER, ""
        )
        self._save_as_old(env, analysis, [gone])
        env.edit_states.save(EditState("l1", 0).restore(gone.id))

        env.service.analyze("r1", lambda s, p: None)

        assert env.edit_states.get("l1").restored_suggestion_ids == frozenset()

    def test_edit_state_is_not_saved_when_nothing_changes(self, env: Env) -> None:
        analysis = env.service.analyze("r1", lambda s, p: None)
        saved = env.edit_states.save(EditState("l1", 0).restore(self._filler_id(analysis)))

        env.service.analyze("r1", lambda s, p: None)

        assert env.edit_states.get("l1") == saved

    def test_unreadable_previous_analysis_is_ignored(self, env: Env) -> None:
        env.service.analyze("r1", lambda s, p: None)
        env.service.store.write_json("r1", "analysis.json", {"古い形": True})
        saved = env.edit_states.save(EditState("l1", 0).restore("r1-c0000-filler-0"))

        env.service.analyze("r1", lambda s, p: None)

        assert env.edit_states.get("l1") == saved

    def test_restorations_of_another_recording_in_the_lecture_stay(self, tmp_path: Path) -> None:
        # まとめたレクチャー（r1・r2）で r1 だけを解析し直しても、r2 の戻した候補には触れない
        merged = build_env(tmp_path, recording_ids=("r1", "r2"))
        analysis = merged.service.analyze("r1", lambda s, p: None)
        old = CutSuggestion("r1-c0000-filler-7", "r1", Interval(1_000, 1_300), CutKind.FILLER, "")
        self._save_as_old(merged, analysis, [old])
        merged.edit_states.save(
            EditState("l1", 0)
            .restore(old.id)
            .restore("r2-c0000-filler-0")
            .restore("r2-silence-0000")
        )

        merged.service.analyze("r1", lambda s, p: None)

        assert merged.edit_states.get("l1").restored_suggestion_ids == frozenset(
            {self._filler_id(analysis), "r2-c0000-filler-0", "r2-silence-0000"}
        )

    def test_retries_when_the_editor_saves_at_the_same_time(self, tmp_path: Path) -> None:
        busy = build_env(tmp_path, conflicts=2)
        analysis = busy.service.analyze("r1", lambda s, p: None)
        old = CutSuggestion("r1-c0000-filler-7", "r1", Interval(1_000, 1_300), CutKind.FILLER, "")
        self._save_as_old(busy, analysis, [old])
        busy.edit_states.save(EditState("l1", 0).restore(old.id))
        busy.colliding.arm()

        busy.service.analyze("r1", lambda s, p: None)

        assert busy.edit_states.get("l1").restored_suggestion_ids == frozenset(
            {self._filler_id(analysis)}
        )

    def test_gives_up_with_a_warning_when_saving_keeps_colliding(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        busy = build_env(tmp_path, conflicts=100)
        analysis = busy.service.analyze("r1", lambda s, p: None)
        old = CutSuggestion("r1-c0000-filler-7", "r1", Interval(1_000, 1_300), CutKind.FILLER, "")
        self._save_as_old(busy, analysis, [old])
        busy.edit_states.save(EditState("l1", 0).restore(old.id))
        busy.colliding.arm()

        # 解析そのものは成功させる（解析結果は書けている）
        again = busy.service.analyze("r1", lambda s, p: None)

        assert again == analysis
        assert busy.edit_states.get("l1").restored_suggestion_ids == frozenset({old.id})
        assert "引き継げませんでした" in caplog.text

    def test_warns_when_the_previous_analysis_cannot_be_read(
        self, env: Env, caplog: pytest.LogCaptureFixture
    ) -> None:
        env.service.analyze("r1", lambda s, p: None)
        env.service.store.write_json("r1", "analysis.json", {"古い形": True})

        env.service.analyze("r1", lambda s, p: None)

        assert "前の解析結果を読めない" in caplog.text
