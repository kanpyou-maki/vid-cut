import sys
from pathlib import Path
from typing import Any

import pytest

from tests.e2e import serve as launcher
from tests.e2e import worker as fake_worker
from tests.e2e.script import ScriptedJudge
from tests.e2e.stage import MARKER
from vidcut.bootstrap import REVEAL_ENV, REVEAL_OFF, App
from vidcut.process import PARENT_PID_FLAG
from vidcut.serve import WORKSPACE_ENV, ServeOptions


def _empty_lesson(dest: Path, tone_hz: int) -> None:
    dest.write_bytes(b"")


class TestServe:
    def test_serves_the_stage_instead_of_the_real_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 実データを指す環境変数があっても、使わない
        monkeypatch.setenv(WORKSPACE_ENV, str(tmp_path / "real"))
        monkeypatch.delenv(REVEAL_ENV, raising=False)
        served: list[tuple[ServeOptions, Any]] = []

        def serve(options: ServeOptions, *, start_worker: Any) -> int:
            served.append((options, start_worker))
            return 0

        root = tmp_path / "root"
        code = launcher.main(
            ["--root", str(root), "--port", "8799", "--frontend-dist", str(tmp_path / "dist")],
            serve=serve,
            make_lesson=_empty_lesson,
        )

        ((options, start_worker),) = served
        assert code == 0
        assert (root / MARKER).is_file()
        assert options == ServeOptions(
            workspace=root.resolve() / "workspace",
            home=root.resolve() / "home",
            frontend_dist=tmp_path / "dist",
            port=8799,
        )
        assert start_worker is launcher.start_fake_worker
        assert not (tmp_path / "real").exists()

    def test_never_opens_finder(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(REVEAL_ENV, raising=False)
        seen: list[str | None] = []

        def serve(options: ServeOptions, *, start_worker: Any) -> int:
            seen.append(launcher.os.environ.get(REVEAL_ENV))
            return 0

        launcher.main(
            ["--root", str(tmp_path / "root"), "--port", "8799", "--frontend-dist", str(tmp_path)],
            serve=serve,
            make_lesson=_empty_lesson,
        )

        assert seen == [REVEAL_OFF]

    def test_starts_the_fake_worker_as_a_child_that_follows_this_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[list[str], dict[str, Any]]] = []

        class Process:
            returncode = 0  # 既に終わっている（stop は何も送らない）

            def poll(self) -> int | None:
                return self.returncode

        def popen(args: list[str], **kwargs: Any) -> Process:
            calls.append((args, kwargs))
            return Process()

        monkeypatch.setattr(launcher.subprocess, "Popen", popen)

        launcher.start_fake_worker(tmp_path / "workspace").stop()

        ((args, kwargs),) = calls
        pid = str(launcher.os.getpid())
        assert args == [sys.executable, "-m", "tests.e2e.worker", PARENT_PID_FLAG, pid]
        assert kwargs["env"][WORKSPACE_ENV] == str(tmp_path / "workspace")
        assert (Path(kwargs["cwd"]) / "tests" / "e2e" / "worker.py").is_file()


class TestWorker:
    def test_runs_the_worker_command_with_the_fake_app(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(WORKSPACE_ENV, str(tmp_path))
        monkeypatch.setenv(REVEAL_ENV, REVEAL_OFF)
        built: list[App] = []

        def run(argv: list[str], *, build: Any) -> int:
            assert argv == ["worker", PARENT_PID_FLAG, "123"]
            built.append(build())
            return 0

        try:
            assert fake_worker.main([PARENT_PID_FLAG, "123"], run=run) == 0
            (app,) = built
            assert app.workspace == tmp_path
            assert isinstance(app.judge._model, ScriptedJudge)
        finally:
            for app in built:
                app.close()
