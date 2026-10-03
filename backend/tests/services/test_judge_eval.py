import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.pipeline.fakes import DirectoryStore, make_recording
from tests.pipeline.judge_fakes import FakeModel, delete_output, make_analysis
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.domain.intervals import Interval
from vidcut.domain.models import Lecture
from vidcut.pipeline.analysis_result import save_analysis
from vidcut.pipeline.judge import JudgeSettings
from vidcut.pipeline.ports import NotFoundError
from vidcut.services.judge_eval import (
    JudgeEvalService,
    load_sample_entries,
    load_truth,
    score_judgement,
)

PROTOTYPE = Path(__file__).parents[3] / "docs" / "references" / "prototype"
DUPLICATED_ID = (
    '[{"id": 0, "start": 0, "end": 1, "text": "a"}, {"id": 0, "start": 2, "end": 3, "text": "b"}]'
)


class TestScore:
    def test_counts_correct_wrong_and_missed(self) -> None:
        score = score_judgement(predicted=[1, 2, 3, 9], truth=[2, 3, 4, 5, 6])
        assert (score.correct, score.wrong, score.missed) == ((2, 3), (1, 9), (4, 5, 6))
        assert score.precision == pytest.approx(0.5)
        assert score.recall == pytest.approx(0.4)
        assert not score.meets_targets

    def test_perfect_match_meets_targets(self) -> None:
        score = score_judgement(predicted=[3, 1], truth=[1, 3])
        assert (score.precision, score.recall) == (1.0, 1.0)
        assert score.meets_targets

    @pytest.mark.parametrize(
        ("correct", "wrong", "missed", "meets"),
        [
            (9, 1, 0, True),
            (8, 1, 2, False),
            (89, 11, 0, False),
            (8, 0, 2, True),
            (79, 0, 21, False),
        ],
    )
    def test_targets_are_90_percent_precision_and_80_percent_recall(
        self, correct: int, wrong: int, missed: int, meets: bool
    ) -> None:
        hits = list(range(correct))
        extra = list(range(1_000, 1_000 + wrong))
        rest = list(range(2_000, 2_000 + missed))
        assert score_judgement(hits + extra, hits + rest).meets_targets is meets

    def test_deleting_nothing_has_full_precision_and_no_recall(self) -> None:
        score = score_judgement(predicted=[], truth=[1])
        assert (score.precision, score.recall) == (1.0, 0.0)

    def test_nothing_to_delete_has_full_recall(self) -> None:
        score = score_judgement(predicted=[1], truth=[])
        assert (score.precision, score.recall) == (0.0, 1.0)


class TestLoadSampleFiles:
    def test_reads_prototype_chunks(self) -> None:
        entries = load_sample_entries(PROTOTYPE / "sample-chunks.json")
        assert len(entries) == 69
        assert [e.number for e in entries] == list(range(69))
        assert entries[4].text == "クライアントから"
        assert entries[4].chunk.span == Interval(24_673, 25_449)

    def test_reads_prototype_truth(self) -> None:
        truth = load_truth(PROTOTYPE / "sample-judge-ground-truth.json")
        assert len(truth) == 21
        assert {3, 32, 66} <= truth

    def test_chunk_without_text_is_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.json"
        chunks = [
            {"id": 0, "start": 0.0, "end": 1.0, "text": "a"},
            {"id": 1, "start": 2.0, "end": 3.0, "text": " "},
        ]
        path.write_text(json.dumps(chunks))
        assert [e.number for e in load_sample_entries(path)] == [0]

    @pytest.mark.parametrize(
        "content",
        [
            "{broken",
            '{"id": 0}',
            '[{"id": 0, "start": 0.0, "end": 1.0}]',
            '[{"id": "x", "start": 0.0, "end": 1.0, "text": "a"}]',
            '[{"id": 0, "start": 2.0, "end": 1.0, "text": "a"}]',
            DUPLICATED_ID,
        ],
    )
    def test_rejects_malformed_chunks(self, tmp_path: Path, content: str) -> None:
        path = tmp_path / "chunks.json"
        path.write_text(content)
        with pytest.raises(ValueError, match=r"chunks\.json"):
            load_sample_entries(path)

    @pytest.mark.parametrize("content", ["{broken", '{"id": 0}', '[{"reason": "x"}]', "[true]"])
    def test_rejects_malformed_truth(self, tmp_path: Path, content: str) -> None:
        path = tmp_path / "truth.json"
        path.write_text(content)
        with pytest.raises(ValueError, match=r"truth\.json"):
            load_truth(path)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="読めません"):
            load_truth(tmp_path / "nope.json")


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = open_database(tmp_path / "db.sqlite3")
    yield connection
    connection.close()


def make_service(
    conn: sqlite3.Connection, tmp_path: Path, outputs: list[str]
) -> tuple[JudgeEvalService, FakeModel, DirectoryStore]:
    model = FakeModel(outputs)
    store = DirectoryStore(tmp_path / "ws")
    service = JudgeEvalService(
        lectures=SqliteLectureRepository(conn),
        store=store,
        model=model,
        settings=JudgeSettings(),
        prompt="指示文\n",
    )
    return service, model, store


class TestRun:
    def test_scores_model_decisions_against_truth(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        entries = load_sample_entries(PROTOTYPE / "sample-chunks.json")
        output = delete_output(
            {"id": 3, "kind": "retake", "reason": "言い直し", "superseded_by": 7},
            {"id": 8, "kind": "noise", "reason": "誤り"},
        )
        service, model, _ = make_service(conn, tmp_path, [output])
        run = service.run(entries, frozenset({3, 4}))
        assert (run.score.correct, run.score.wrong, run.score.missed) == ((3,), (8,), (4,))
        assert [d.number for d in run.decisions] == [3, 8]
        assert model.prompts[0].startswith("指示文\n0\t8.2\t11.3\t前のレクチャー")

    def test_rejects_truth_for_chunks_that_are_not_listed(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        entries = load_sample_entries(PROTOTYPE / "sample-chunks.json")
        service, model, _ = make_service(conn, tmp_path, [])
        with pytest.raises(ValueError, match="正解データ"):
            service.run(entries, frozenset({3, 500}))
        assert model.prompts == []


class TestLectureEntries:
    def setup_lectures(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        recordings = SqliteRecordingRepository(conn)
        lectures = SqliteLectureRepository(conn)
        for index, title in enumerate(("S05-12", "S05-13", "S05-13")):
            rid = f"r{index}"
            recordings.add(make_recording(tmp_path / f"{rid}.mov", rid))
            lectures.save(Lecture(id=f"l{index}", title=title, recording_ids=(rid,)))

    def test_finds_lecture_by_title_or_id(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        self.setup_lectures(conn, tmp_path)
        service, _, store = make_service(conn, tmp_path, [])
        save_analysis(store, make_analysis("r0", ("こんにちは", "えー")))
        by_title = service.lecture_entries("S05-12")
        assert [e.text for e in by_title] == ["こんにちは", "えー"]
        assert service.lecture_entries("l0") == by_title

    def test_unknown_lecture(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        self.setup_lectures(conn, tmp_path)
        service, _, _ = make_service(conn, tmp_path, [])
        with pytest.raises(NotFoundError, match="S99"):
            service.lecture_entries("S99")

    def test_ambiguous_title_lists_candidate_ids(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        self.setup_lectures(conn, tmp_path)
        service, _, _ = make_service(conn, tmp_path, [])
        with pytest.raises(ValueError, match=r"l1.*l2"):
            service.lecture_entries("S05-13")

    def test_lecture_not_analyzed(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        self.setup_lectures(conn, tmp_path)
        service, _, _ = make_service(conn, tmp_path, [])
        with pytest.raises(NotFoundError, match="解析"):
            service.lecture_entries("S05-12")
