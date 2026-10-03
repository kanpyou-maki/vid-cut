import json
import os
import signal
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from tests.pipeline.fakes import FakeAligner, FakeMediaTool, FakeTranscriber, FakeVad
from tests.pipeline.judge_fakes import FakeModel, delete_output
from vidcut.bootstrap import App, MlTools, build_app
from vidcut.cli import main, openapi_text
from vidcut.domain.models import Job, JobKind, JobStatus
from vidcut.pipeline.ports import LoginRequiredError
from vidcut.serve import DEFAULT_PORT, ServeOptions

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


class TestWorkerWithParent:
    def test_worker_stops_when_the_given_parent_is_not_its_parent(self, tmp_path: Path) -> None:
        # vidcut serve は自分のプロセス番号を渡す。それが親でなくなっていたら、worker は止まる
        not_my_parent = os.getppid() + 1
        code = main(
            ["worker", "--parent-pid", str(not_my_parent)], build=fake_build(tmp_path / "ws")
        )
        assert code == 0

    def test_worker_keeps_running_while_the_given_parent_is_alive(self, tmp_path: Path) -> None:
        stop = threading.Event()
        threading.Timer(0.3, stop.set).start()
        code = main(
            ["worker", "--parent-pid", str(os.getppid())],
            build=fake_build(tmp_path / "ws"),
            stop=stop,
        )
        assert code == 0


class TestWorkerInterrupt:
    def test_sigterm_stops_the_worker_like_ctrl_c(self, tmp_path: Path) -> None:
        previous = signal.getsignal(signal.SIGTERM)
        timer = threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM))
        timer.start()
        try:
            code = main(["worker"], build=fake_build(tmp_path / "ws"))
        finally:
            timer.cancel()
            signal.signal(signal.SIGTERM, previous)
        assert code == 130


class TestServe:
    def run(self, argv: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ServeOptions:
        monkeypatch.setenv("VIDCUT_WORKSPACE", str(tmp_path / "ws"))
        monkeypatch.setenv("VIDCUT_FRONTEND_DIST", str(tmp_path / "dist"))
        received: list[ServeOptions] = []

        def fake_serve(options: ServeOptions) -> int:
            received.append(options)
            return 0

        def never_build() -> App:
            raise AssertionError("serve は worker 用の組み立て（ML・claude）を使わない")

        assert main(argv, build=never_build, serve=fake_serve) == 0
        return received[0]

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        options = self.run(["serve"], monkeypatch, tmp_path)
        assert options == ServeOptions(
            workspace=tmp_path / "ws",
            home=Path.home(),
            frontend_dist=tmp_path / "dist",
            port=DEFAULT_PORT,
            dev=False,
            with_worker=True,
        )

    def test_flags(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        options = self.run(
            ["serve", "--port", "9123", "--dev", "--no-worker"], monkeypatch, tmp_path
        )
        assert (options.port, options.dev, options.with_worker) == (9123, True, False)

    @pytest.mark.parametrize("port", ["0", "80", "1023", "65536", "abc", "-1", "８７６５"])
    def test_port_must_be_an_unprivileged_port(self, port: str) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["serve", "--port", port], serve=lambda options: 0)
        assert exit_info.value.code == 2

    @pytest.mark.parametrize("port", [1024, 65535])
    def test_ports_at_the_ends_of_the_range_are_accepted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, port: int
    ) -> None:
        assert self.run(["serve", "--port", str(port)], monkeypatch, tmp_path).port == port


class TestOpenapi:
    def test_prints_the_schema_of_the_api(self, capsys: pytest.CaptureFixture[str]) -> None:
        def never_build() -> App:
            raise AssertionError("openapi はワークスペースを開かない")

        assert main(["openapi"], build=never_build) == 0
        schema = json.loads(capsys.readouterr().out)
        assert "/api/lectures/{lecture_id}/edits" in schema["paths"]
        assert "ErrorOut" in schema["components"]["schemas"]

    def test_writes_the_schema_to_a_file_in_a_stable_form(self, tmp_path: Path) -> None:
        output = tmp_path / "generated" / "openapi.json"
        assert main(["openapi", "--output", str(output)]) == 0
        text = output.read_text(encoding="utf-8")
        assert main(["openapi", "--output", str(output)]) == 0
        assert output.read_text(encoding="utf-8") == text  # 何度出しても同じ（差分が出ない）
        assert text.endswith("\n")
        assert "編集状態の版が古い" in text  # 日本語をエスケープしない
        assert list(json.loads(text)) == sorted(json.loads(text))

    def test_committed_schema_matches_the_api(self) -> None:
        # frontend の型（src/api/generated/schema.d.ts）は、このファイルから作る。
        # API を変えたら `npm --prefix frontend run gen:api` で作り直すこと
        committed = Path(__file__).parents[3] / "frontend/src/api/generated/openapi.json"
        assert committed.read_text(encoding="utf-8") == openapi_text()
