"""`vidcut serve` の組み立て（ADR-004、Design Doc 3-5-1）。サーバーと worker は偽物に差し替える。"""

import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vidcut.api.frontend import TOKEN_META
from vidcut.api.security import TOKEN_HEADER
from vidcut.process import interrupt_on_sigterm, stop_when_parent_exits
from vidcut.serve import (
    DEFAULT_PORT,
    FRONTEND_DIST_ENV,
    HOST,
    VITE_ORIGINS,
    ServeOptions,
    WorkerProcess,
    default_frontend_dist,
    frontend_build_is_stale,
    serve,
    start_worker_process,
)


@dataclass
class FakeServer:
    """uvicorn の代わり。渡されたアプリと待ち受け先を覚えて、すぐ戻る。"""

    error: Exception | None = None
    calls: list[tuple[FastAPI, str, int]] = field(default_factory=list)

    def __call__(self, app: FastAPI, host: str, port: int) -> None:
        self.calls.append((app, host, port))
        if self.error is not None:
            raise self.error

    @property
    def app(self) -> FastAPI:
        return self.calls[-1][0]


@dataclass
class FakeWorker:
    """worker プロセスの代わり。起動と停止を記録する。"""

    events: list[str] = field(default_factory=list)
    workspaces: list[Path] = field(default_factory=list)

    def start(self, workspace: Path) -> "FakeWorker":
        self.events.append("start")
        self.workspaces.append(workspace)
        return self

    def stop(self) -> None:
        self.events.append("stop")


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head></head><body></body></html>")
    return dist


def options(tmp_path: Path, dist: Path, **changes: Any) -> ServeOptions:
    base = ServeOptions(workspace=tmp_path / "ws", home=tmp_path, frontend_dist=dist)
    return replace(base, **changes)


def page_token(client: TestClient) -> str:
    """画面の HTML に埋め込まれたトークン。"""
    found = re.search(rf'<meta name="{TOKEN_META}" content="([^"]+)"', client.get("/").text)
    assert found is not None
    return found.group(1)


def client_for(server: FakeServer, port: int = DEFAULT_PORT) -> TestClient:
    return TestClient(server.app, base_url=f"http://{HOST}:{port}")


class TestServe:
    def test_listens_on_loopback_only(self, tmp_path: Path, dist: Path) -> None:
        server, worker = FakeServer(), FakeWorker()
        code = serve(options(tmp_path, dist), run_server=server, start_worker=worker.start)
        assert code == 0
        ((_, host, port),) = server.calls
        assert (host, port) == ("127.0.0.1", DEFAULT_PORT)

    def test_page_token_opens_the_api(self, tmp_path: Path, dist: Path) -> None:
        server, worker = FakeServer(), FakeWorker()
        serve(options(tmp_path, dist), run_server=server, start_worker=worker.start)
        client = client_for(server)
        token = page_token(client)
        assert client.get("/api/lectures").status_code == 401
        response = client.get("/api/lectures", headers={TOKEN_HEADER: token})
        assert response.json() == {"success": True, "data": [], "error": None}

    def test_token_is_new_on_every_launch_and_never_printed(
        self, tmp_path: Path, dist: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tokens = []
        for _ in range(2):
            server, worker = FakeServer(), FakeWorker()
            serve(options(tmp_path, dist), run_server=server, start_worker=worker.start)
            tokens.append(page_token(client_for(server)))
        printed = capsys.readouterr()
        assert tokens[0] != tokens[1]
        assert all(token not in printed.out + printed.err for token in tokens)
        assert f"http://127.0.0.1:{DEFAULT_PORT}/" in printed.out

    def test_guard_follows_the_port(self, tmp_path: Path, dist: Path) -> None:
        server, worker = FakeServer(), FakeWorker()
        serve(options(tmp_path, dist, port=9123), run_server=server, start_worker=worker.start)
        assert server.calls[0][2] == 9123
        assert client_for(server, 9123).get("/").status_code == 200
        assert client_for(server, DEFAULT_PORT).get("/").status_code == 403

    def test_creates_the_workspace_database(self, tmp_path: Path, dist: Path) -> None:
        serve(options(tmp_path, dist), run_server=FakeServer(), start_worker=FakeWorker().start)
        assert (tmp_path / "ws" / "vidcut.sqlite3").is_file()

    def test_file_browser_is_limited_to_the_home(self, tmp_path: Path, dist: Path) -> None:
        server = FakeServer()
        serve(options(tmp_path, dist), run_server=server, start_worker=FakeWorker().start)
        client = client_for(server)
        headers = {TOKEN_HEADER: page_token(client)}
        assert client.get("/api/fs", headers=headers).json()["data"]["path"] == str(
            tmp_path.resolve()
        )
        assert client.get("/api/fs", params={"path": "/etc"}, headers=headers).status_code == 422


@pytest.fixture(autouse=True)
def restore_sigterm() -> Iterator[None]:
    """serve は SIGTERM の扱いを変える。ほかのテストに残さない。"""
    previous = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, previous)


class TestWorkerProcess:
    def test_sigterm_is_handled_before_the_worker_starts(self, tmp_path: Path, dist: Path) -> None:
        # worker を起動してからサーバーが動くまでの間に止められても、worker を残さない
        handlers = []

        def start(workspace: Path) -> FakeWorker:
            handlers.append(signal.getsignal(signal.SIGTERM))
            return FakeWorker()

        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        serve(options(tmp_path, dist), run_server=FakeServer(), start_worker=start)
        assert handlers[0] is not signal.SIG_DFL
        with pytest.raises(KeyboardInterrupt):
            signal.raise_signal(signal.SIGTERM)

    def test_worker_runs_while_the_server_does(self, tmp_path: Path, dist: Path) -> None:
        worker = FakeWorker()

        def server(app: FastAPI, host: str, port: int) -> None:
            assert worker.events == ["start"]  # サーバーが動いている間、worker も動いている

        serve(options(tmp_path, dist), run_server=server, start_worker=worker.start)
        assert worker.events == ["start", "stop"]
        assert worker.workspaces == [tmp_path / "ws"]

    def test_worker_is_stopped_even_if_the_server_fails(self, tmp_path: Path, dist: Path) -> None:
        # ポートが使われているなどでサーバーが落ちても、worker を残さない
        server, worker = FakeServer(error=OSError("address already in use")), FakeWorker()
        with pytest.raises(OSError, match="in use"):
            serve(options(tmp_path, dist), run_server=server, start_worker=worker.start)
        assert worker.events == ["start", "stop"]

    def test_interrupt_is_a_normal_stop(self, tmp_path: Path, dist: Path) -> None:
        # Ctrl+C と SIGTERM は「止める」合図。エラーにせず、worker を止めて終わる
        server, worker = FakeServer(error=KeyboardInterrupt()), FakeWorker()
        code = serve(options(tmp_path, dist), run_server=server, start_worker=worker.start)
        assert code == 0
        assert worker.events == ["start", "stop"]

    def test_signal_handling_is_left_alone_outside_the_main_thread(self) -> None:
        # シグナルの扱いはメインスレッドでしか変えられない。ほかのスレッドでは何もしない
        before = signal.getsignal(signal.SIGTERM)
        thread = threading.Thread(target=interrupt_on_sigterm)
        thread.start()
        thread.join(timeout=5)
        assert signal.getsignal(signal.SIGTERM) is before

    def test_sigterm_is_turned_into_an_interrupt(self) -> None:
        # uvicorn は止まったあとに SIGTERM を送り直す。既定の動作のままだと、その場でプロセスが
        # 終わって worker を止められない
        previous = signal.getsignal(signal.SIGTERM)
        try:
            interrupt_on_sigterm()
            with pytest.raises(KeyboardInterrupt):
                signal.raise_signal(signal.SIGTERM)
        finally:
            signal.signal(signal.SIGTERM, previous)

    def test_server_is_not_started_if_the_worker_cannot_start(
        self, tmp_path: Path, dist: Path
    ) -> None:
        def failing_start(workspace: Path) -> FakeWorker:
            raise OSError("worker を起動できません")

        server = FakeServer()
        with pytest.raises(OSError, match="worker"):
            serve(options(tmp_path, dist), run_server=server, start_worker=failing_start)
        assert server.calls == []

    def test_nothing_is_started_if_the_workspace_cannot_be_opened(
        self, tmp_path: Path, dist: Path
    ) -> None:
        blocked = tmp_path / "file"
        blocked.write_text("ワークスペースの場所にファイルがある")
        server, worker = FakeServer(), FakeWorker()
        with pytest.raises(OSError):
            serve(
                options(tmp_path, dist, workspace=blocked / "ws"),
                run_server=server,
                start_worker=worker.start,
            )
        assert (server.calls, worker.events) == ([], [])

    def test_server_can_run_without_a_worker(self, tmp_path: Path, dist: Path) -> None:
        server, worker = FakeServer(), FakeWorker()
        serve(
            options(tmp_path, dist, with_worker=False),
            run_server=server,
            start_worker=worker.start,
        )
        assert worker.events == []
        assert len(server.calls) == 1


class TestDevelopmentMode:
    @pytest.mark.parametrize("origin", VITE_ORIGINS)
    def test_vite_origin_is_accepted_only_in_development(
        self, tmp_path: Path, dist: Path, origin: str
    ) -> None:
        statuses = {}
        for dev in (False, True):
            server = FakeServer()
            serve(
                options(tmp_path, dist, dev=dev), run_server=server, start_worker=FakeWorker().start
            )
            statuses[dev] = client_for(server).get("/", headers={"Origin": origin}).status_code
        assert statuses == {False: 403, True: 200}


STALE_NOTE = "画面のビルドが、ソースより古い"


def frontend_with_sources(tmp_path: Path, *, built_at: float, changed: dict[str, float]) -> Path:
    """frontend/dist（index.html の更新時刻が built_at）と、src のファイル（名前 → 更新時刻）。"""
    frontend = tmp_path / "frontend"
    built = frontend / "dist"
    built.mkdir(parents=True)
    index = built / "index.html"
    index.write_text("<!doctype html><html><head></head><body></body></html>", encoding="utf-8")
    os.utime(index, (built_at, built_at))
    for name, modified in changed.items():
        source = frontend / "src" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("export {};", encoding="utf-8")
        os.utime(source, (modified, modified))
    return built


class TestStaleFrontendBuild:
    """ビルドし直さないと、古い画面を配信し続ける（受け入れチェックで、新しい画面が出なかった）。"""

    def launch(self, tmp_path: Path, built: Path, **changes: Any) -> None:
        serve(
            options(tmp_path, built, **changes),
            run_server=FakeServer(),
            start_worker=FakeWorker().start,
        )

    def test_warns_when_a_source_is_newer_than_the_build(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        built = frontend_with_sources(
            tmp_path, built_at=1_000, changed={"editor/PaddingSettings.tsx": 2_000}
        )
        self.launch(tmp_path, built)
        out = capsys.readouterr().out
        assert STALE_NOTE in out
        assert "npm --prefix frontend run build" in out

    def test_is_quiet_when_the_build_is_up_to_date(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        built = frontend_with_sources(tmp_path, built_at=2_000, changed={"main.tsx": 1_000})
        self.launch(tmp_path, built)
        assert STALE_NOTE not in capsys.readouterr().out

    def test_ignores_tests_and_test_helpers(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # テストは、ビルドの出力に入らない
        changed = {"editor/keepRanges.test.ts": 2_000, "test/fakeApi.ts": 2_000, "main.tsx": 500}
        built = frontend_with_sources(tmp_path, built_at=1_000, changed=changed)
        self.launch(tmp_path, built)
        assert STALE_NOTE not in capsys.readouterr().out

    def test_a_source_as_old_as_the_build_is_not_newer(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        built = frontend_with_sources(tmp_path, built_at=1_000, changed={"main.tsx": 1_000})
        self.launch(tmp_path, built)
        assert STALE_NOTE not in capsys.readouterr().out

    def test_looks_into_nested_folders(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        changed = {"main.tsx": 500, "editor/parts/deep/Field.tsx": 2_000}
        built = frontend_with_sources(tmp_path, built_at=1_000, changed=changed)
        self.launch(tmp_path, built)
        assert STALE_NOTE in capsys.readouterr().out

    def test_only_the_top_level_test_folder_is_ignored(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # テストの補助は src/test/ に置く決まり。ほかの test フォルダは、画面のコードとして見る
        built = frontend_with_sources(
            tmp_path, built_at=1_000, changed={"editor/test/helper.ts": 2_000}
        )
        self.launch(tmp_path, built)
        assert STALE_NOTE in capsys.readouterr().out

    def test_a_file_whose_time_cannot_be_read_does_not_stop_the_launch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        built = frontend_with_sources(tmp_path, built_at=1_000, changed={"main.tsx": 2_000})
        real_stat = Path.stat

        def stat(self: Path, **kwargs: Any) -> os.stat_result:
            if self.name == "main.tsx":
                raise PermissionError("読めない")
            return real_stat(self, **kwargs)

        monkeypatch.setattr(Path, "stat", stat)
        self.launch(tmp_path, built)
        assert STALE_NOTE not in capsys.readouterr().out

    def test_no_build_location_means_not_stale(self) -> None:
        assert frontend_build_is_stale(None) is False

    def test_is_quiet_without_the_sources(
        self, tmp_path: Path, dist: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # リポジトリの外に置いたビルド（ソースが隣にない）は、比べようがない
        self.launch(tmp_path, dist)
        assert STALE_NOTE not in capsys.readouterr().out

    def test_is_quiet_without_a_build(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # ビルドがなければ、画面がビルドの案内を出す（ここでは警告しない）
        built = frontend_with_sources(tmp_path, built_at=1_000, changed={"main.tsx": 2_000})
        (built / "index.html").unlink()
        self.launch(tmp_path, built)
        assert STALE_NOTE not in capsys.readouterr().out

    def test_a_file_that_cannot_be_read_does_not_stop_the_launch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 知らせるための確認で、起動を止めない
        built = frontend_with_sources(tmp_path, built_at=1_000, changed={"main.tsx": 2_000})

        def unreadable(self: Path, pattern: str) -> Iterator[Path]:
            raise PermissionError("読めない")

        monkeypatch.setattr(Path, "rglob", unreadable)
        self.launch(tmp_path, built)
        assert STALE_NOTE not in capsys.readouterr().out

    def test_is_quiet_in_development(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # 開発中は Vite が画面を配信するので、ビルドは使わない
        built = frontend_with_sources(tmp_path, built_at=1_000, changed={"main.tsx": 2_000})
        self.launch(tmp_path, built, dev=True)
        assert STALE_NOTE not in capsys.readouterr().out


class TestDefaultFrontendDist:
    def test_points_at_the_build_in_this_repository(self) -> None:
        dist = default_frontend_dist({})
        assert dist.parts[-2:] == ("frontend", "dist")
        assert (dist.parent / "package.json").is_file()

    def test_home_in_the_environment_value_is_expanded(self) -> None:
        dist = default_frontend_dist({FRONTEND_DIST_ENV: "~/vidcut-dist"})
        assert dist == Path.home() / "vidcut-dist"

    def test_can_be_changed_by_the_environment(self, tmp_path: Path) -> None:
        assert default_frontend_dist({FRONTEND_DIST_ENV: str(tmp_path)}) == tmp_path


def sleeping_process(code: str = "import time; time.sleep(60)") -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.DEVNULL)


class TestWorkerProcessStop:
    def test_terminates_a_running_process(self) -> None:
        process = sleeping_process()
        WorkerProcess(process).stop()
        assert process.poll() is not None

    def test_process_that_already_exited_is_reported(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        process = sleeping_process("raise SystemExit(3)")
        process.wait()
        WorkerProcess(process).stop()
        assert "終了コード 3" in caplog.text

    def test_process_that_ignores_the_request_is_killed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        ignoring = (
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN);"
            "print('ready', flush=True); time.sleep(60)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", ignoring], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE
        )
        assert process.stdout is not None and process.stdout.readline() == b"ready\n"
        WorkerProcess(process, stop_timeout_s=0.3).stop()
        assert process.poll() == -signal.SIGKILL
        assert "強制終了" in caplog.text


@pytest.mark.integration
def test_worker_process_serves_the_given_workspace(tmp_path: Path) -> None:
    worker = start_worker_process(tmp_path / "ws")
    try:
        deadline = time.monotonic() + 30
        while not (tmp_path / "ws" / "vidcut.sqlite3").exists():
            assert time.monotonic() < deadline, "worker がワークスペースを開きませんでした"
            time.sleep(0.1)
    finally:
        worker.stop()


class TestStopWhenParentExits:
    def test_stops_once_the_parent_changes(self) -> None:
        # 親（vidcut serve）が強制終了されると、子の親は別のプロセス（launchd）に変わる
        parents = iter([100, 100, 1])
        stop = threading.Event()
        watcher = stop_when_parent_exits(
            stop, 100, get_parent=lambda: next(parents, 1), poll_interval_s=0.01
        )
        watcher.join(timeout=5)
        assert stop.is_set()
        assert not watcher.is_alive()

    def test_stops_at_once_if_the_parent_is_already_gone(self) -> None:
        # worker の起動（読み込みに数秒かかる）の間に親が終わっていても、気づけること
        stop = threading.Event()
        watcher = stop_when_parent_exits(stop, 100, get_parent=lambda: 1, poll_interval_s=60)
        watcher.join(timeout=5)
        assert stop.is_set()

    def test_keeps_running_while_the_parent_is_alive(self) -> None:
        stop = threading.Event()
        watcher = stop_when_parent_exits(stop, 100, get_parent=lambda: 100, poll_interval_s=0.01)
        time.sleep(0.1)
        assert not stop.is_set()
        stop.set()  # worker が別の理由で止まれば、見張りも終わる
        watcher.join(timeout=5)
        assert not watcher.is_alive()
