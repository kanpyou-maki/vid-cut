from pathlib import Path

from vidcut.bootstrap import build_app, workspace_from_env
from vidcut.domain.models import JobKind


def test_workspace_defaults_to_home_vidcut() -> None:
    assert workspace_from_env({}) == Path.home() / "VidCut"


def test_workspace_from_environment_variable(tmp_path: Path) -> None:
    assert workspace_from_env({"VIDCUT_WORKSPACE": str(tmp_path / "ws")}) == tmp_path / "ws"


def test_workspace_expands_home() -> None:
    assert workspace_from_env({"VIDCUT_WORKSPACE": "~/x"}) == Path.home() / "x"


def test_build_app_creates_database_and_worker(tmp_path: Path) -> None:
    app = build_app(tmp_path / "ws")
    try:
        assert (tmp_path / "ws" / "vidcut.sqlite3").exists()
        assert {JobKind.ANALYZE_RECORDING, JobKind.MAKE_MEZZANINE} <= set(app.handlers)
        assert app.worker().run_once() is None
    finally:
        app.close()
