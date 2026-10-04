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
from vidcut.pipeline.ports import NotFoundError
from vidcut.services.analysis import AnalysisService


@dataclass
class Env:
    service: AnalysisService
    edit_states: SqliteEditStateRepository


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    conn: sqlite3.Connection = open_database(tmp_path / "db.sqlite3")
    source = tmp_path / "a.mov"
    source.write_bytes(b"mov")
    recordings = SqliteRecordingRepository(conn)
    recordings.add(make_recording(source))
    lectures = SqliteLectureRepository(conn)
    lectures.save(Lecture(id="l1", title="a", recording_ids=("r1",)))
    edit_states = SqliteEditStateRepository(conn)
    tools = AnalysisTools(
        media=FakeMediaTool(),
        vad=FakeVad(),
        transcriber=FakeTranscriber(),
        aligner=FakeAligner(),
        store=DirectoryStore(tmp_path / "ws"),
    )
    service = AnalysisService(
        recordings, tools, AnalysisSettings(), lectures=lectures, edit_states=edit_states
    )
    yield Env(service, edit_states)
    conn.close()


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
