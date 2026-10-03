import json
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from tests.pipeline.fakes import FakeAligner, FakeMediaTool, FakeTranscriber, FakeVad
from tests.pipeline.judge_fakes import FakeModel, delete_output
from vidcut.bootstrap import App, MlTools, build_app
from vidcut.cli import main
from vidcut.domain.models import Job, JobKind, JobStatus
from vidcut.pipeline.ports import LoginRequiredError

KEEP_ALL = '{"delete": []}'


def fake_build(
    workspace: Path, outputs: Sequence[str | Exception] = (KEEP_ALL,)
) -> Callable[[], App]:
    """偽の解析は 2 チャンク（「えーと」「こんにちは」）を作る。outputs は判定の出力。"""

    def build() -> App:
        return build_app(
            workspace,
            media=FakeMediaTool(),
            ml=MlTools(vad=FakeVad(), transcriber=FakeTranscriber(), aligner=FakeAligner()),
            model=FakeModel(outputs),
        )

    return build


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "S05-12.mov"
    path.write_bytes(b"mov")
    return path


def statuses(workspace: Path) -> list[JobStatus]:
    app = fake_build(workspace)()
    try:
        return [stored.job.status for stored in app.queue.list_all()]
    finally:
        app.close()


class TestAnalyze:
    def test_enqueues_without_processing(
        self, tmp_path: Path, video: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["analyze", str(video)], build=fake_build(tmp_path / "ws"))
        out = capsys.readouterr().out
        assert code == 0
        assert "登録: 1 本" in out
        assert "vidcut worker" in out
        assert statuses(tmp_path / "ws") == [JobStatus.QUEUED, JobStatus.QUEUED]

    def test_wait_processes_all_jobs(
        self, tmp_path: Path, video: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["analyze", str(video), "--wait"], build=fake_build(tmp_path / "ws"))
        out = capsys.readouterr().out
        assert code == 0
        assert "成功: 3 件" in out  # 解析 → 判定 → 中間素材
        assert statuses(tmp_path / "ws") == [JobStatus.SUCCEEDED] * 3

    def test_wait_judges_the_lecture_after_analysis(self, tmp_path: Path, video: Path) -> None:
        output = delete_output({"id": 0, "kind": "noise", "reason": "フィラーだけ"})
        build = fake_build(tmp_path / "ws", [output])
        assert main(["analyze", str(video), "--wait"], build=build) == 0
        app = fake_build(tmp_path / "ws")()
        try:
            (lecture,) = app.lectures.list_all()
            judgement = app.judgements.get(lecture.id)
        finally:
            app.close()
        assert judgement is not None
        assert [s.reason for s in judgement.suggestions] == ["フィラーだけ"]

    def test_failed_judgement_is_reported_but_analysis_remains(
        self, tmp_path: Path, video: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build = fake_build(tmp_path / "ws", [LoginRequiredError("`claude` で `/login` が必要です")])
        code = main(["analyze", str(video), "--wait"], build=build)
        out = capsys.readouterr().out
        assert code == 1
        assert "成功: 2 件 / 失敗: 1 件" in out
        assert "/login" in out

    def test_failed_import_returns_error_code(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["analyze", str(tmp_path / "missing.mov")], build=fake_build(tmp_path / "ws"))
        assert code == 1
        assert "missing.mov" in capsys.readouterr().out

    def test_failed_job_returns_error_code(
        self, tmp_path: Path, video: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["analyze", str(video)], build=fake_build(tmp_path / "ws"))
        video.unlink()  # 解析の前に元の録画ファイルが消えた
        code = main(
            ["analyze", str(tmp_path / "other.mov"), "--wait"], build=fake_build(tmp_path / "ws")
        )
        out = capsys.readouterr().out
        assert code == 1
        assert "失敗: 2 件" in out


class TestWorker:
    def test_recovers_interrupted_jobs_then_stops(self, tmp_path: Path) -> None:
        build = fake_build(tmp_path / "ws")
        app = build()
        app.queue.enqueue(Job(id="j1", kind=JobKind.ANALYZE_RECORDING, target_id="r"))
        app.queue.claim_next()
        app.close()
        stop = threading.Event()
        stop.set()
        assert main(["worker"], build=build, stop=stop) == 0
        assert statuses(tmp_path / "ws") == [JobStatus.QUEUED]


def test_requires_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2


def write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class TestEvalJudge:
    @pytest.fixture
    def chunks(self, tmp_path: Path) -> Path:
        texts = ("クライアントから", "クライアントから送られてくる値を", "信用してはいけません")
        return write_json(
            tmp_path / "chunks.json",
            [
                {"id": i, "start": i * 2.0, "end": i * 2.0 + 1.5, "text": t}
                for i, t in enumerate(texts)
            ],
        )

    @pytest.fixture
    def truth(self, tmp_path: Path) -> Path:
        return write_json(tmp_path / "truth.json", [{"id": 0, "reason": "id 1 で言い直し"}])

    def test_reports_precision_and_recall(
        self, tmp_path: Path, chunks: Path, truth: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        output = delete_output({"id": 0, "kind": "retake", "reason": "直後に言い直し"})
        code = main(
            ["eval", "judge", "--chunks", str(chunks), "--truth", str(truth)],
            build=fake_build(tmp_path / "ws", [output]),
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "適合率 100.0%（1/1）" in out
        assert "再現率 100.0%（1/1）" in out
        assert "達成" in out

    def test_lists_wrong_and_missed_chunks_and_fails_below_target(
        self, tmp_path: Path, chunks: Path, truth: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        output = delete_output({"id": 2, "kind": "noise", "reason": "独り言に見える"})
        code = main(
            ["eval", "judge", "--chunks", str(chunks), "--truth", str(truth)],
            build=fake_build(tmp_path / "ws", [output]),
        )
        out = capsys.readouterr().out
        assert code == 1
        assert "適合率 0.0%（0/1）" in out
        assert "再現率 0.0%（0/1）" in out
        assert "誤って削除 2 信用してはいけません（noise: 独り言に見える）" in out
        assert "見逃し 0 クライアントから" in out
        assert "未達" in out

    def test_repeats_runs(
        self, tmp_path: Path, chunks: Path, truth: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        good = delete_output({"id": 0, "kind": "retake", "reason": "直後に言い直し"})
        code = main(
            ["eval", "judge", "--chunks", str(chunks), "--truth", str(truth), "--runs", "2"],
            build=fake_build(tmp_path / "ws", [good, KEEP_ALL]),
        )
        out = capsys.readouterr().out
        assert code == 1  # 1 回でも目標に届かなければ未達
        assert "1 回目" in out
        assert "2 回目" in out

    def test_judges_analyzed_lecture_by_title(
        self, tmp_path: Path, video: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["analyze", str(video), "--wait"], build=fake_build(tmp_path / "ws"))
        truth = write_json(tmp_path / "truth.json", [{"id": 0, "reason": "フィラー"}])
        output = delete_output({"id": 0, "kind": "noise", "reason": "フィラーだけ"})
        code = main(
            ["eval", "judge", "--lecture", "S05-12", "--truth", str(truth)],
            build=fake_build(tmp_path / "ws", [output]),
        )
        assert code == 0
        assert "再現率 100.0%（1/1）" in capsys.readouterr().out

    def test_unknown_lecture(
        self, tmp_path: Path, truth: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(
            ["eval", "judge", "--lecture", "S99", "--truth", str(truth)],
            build=fake_build(tmp_path / "ws"),
        )
        assert code == 1
        assert "S99" in capsys.readouterr().out

    def test_not_logged_in(
        self, tmp_path: Path, chunks: Path, truth: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        error = LoginRequiredError("`claude` を起動して `/login` を実行してください")
        code = main(
            ["eval", "judge", "--chunks", str(chunks), "--truth", str(truth)],
            build=fake_build(tmp_path / "ws", [error]),
        )
        assert code == 1
        assert "/login" in capsys.readouterr().out

    def test_unreadable_files(
        self, tmp_path: Path, truth: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(
            ["eval", "judge", "--chunks", str(tmp_path / "nope.json"), "--truth", str(truth)],
            build=fake_build(tmp_path / "ws"),
        )
        assert code == 1
        assert "nope.json" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "args",
        [
            ["eval", "judge", "--truth", "t.json"],
            ["eval", "judge", "--chunks", "c.json"],
            ["eval", "judge", "--chunks", "c.json", "--lecture", "x", "--truth", "t.json"],
            ["eval", "judge", "--chunks", "c.json", "--truth", "t.json", "--runs", "0"],
            ["eval"],
        ],
    )
    def test_rejects_incomplete_arguments(self, args: list[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(args)
        assert exit_info.value.code == 2
