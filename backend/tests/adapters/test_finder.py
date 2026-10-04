import logging
import subprocess
from pathlib import Path
from typing import Any

import pytest

from vidcut.adapters import finder
from vidcut.adapters.finder import FinderRevealer, LoggingRevealer
from vidcut.pipeline.ports import RevealFailedError


class FakeRun:
    """subprocess.run の偽物。呼ばれ方を覚える（open を実際には実行しない）。"""

    def __init__(self, returncode: int = 0, error: Exception | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.returncode = returncode
        self.error = error

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(args, self.returncode, "", "open: 何かの失敗")


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> FakeRun:
    fake = FakeRun()
    monkeypatch.setattr(finder.subprocess, "run", fake)
    return fake


class TestFinderRevealer:
    def test_selects_the_path_in_finder_without_opening_it(self, run: FakeRun) -> None:
        FinderRevealer().reveal(Path("/Users/me/VidCut/exports/講座 1/講座 1.xml"))
        ((args, kwargs),) = run.calls
        # -R は Finder で選ぶだけ（フォルダ名が foo.app でも、アプリとして起動しない）
        assert args == ["/usr/bin/open", "-R", "/Users/me/VidCut/exports/講座 1/講座 1.xml"]
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert 0 < kwargs["timeout"] <= 30
        assert not kwargs.get("shell", False)

    @pytest.mark.parametrize("path", ["exports/L", "-R", "./L.xml", "~/VidCut"])
    def test_refuses_a_path_that_is_not_absolute(self, run: FakeRun, path: str) -> None:
        with pytest.raises(ValueError, match="絶対パス"):
            FinderRevealer().reveal(Path(path))
        assert run.calls == []

    def test_failure_of_open_is_reported(self, run: FakeRun) -> None:
        run.returncode = 1
        with pytest.raises(RevealFailedError, match="何かの失敗"):
            FinderRevealer().reveal(Path("/tmp/x"))

    @pytest.mark.parametrize(
        "error",
        [subprocess.TimeoutExpired("open", 10), FileNotFoundError("open"), PermissionError()],
    )
    def test_open_that_cannot_run_or_hangs_is_reported(
        self, run: FakeRun, error: Exception
    ) -> None:
        run.error = error
        with pytest.raises(RevealFailedError):
            FinderRevealer().reveal(Path("/tmp/x"))


class TestLoggingRevealer:
    def test_only_logs_the_place(self, run: FakeRun, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            LoggingRevealer().reveal(Path("/Users/me/VidCut/exports/L/L.xml"))
        assert run.calls == []
        assert "/Users/me/VidCut/exports/L/L.xml" in caplog.text
