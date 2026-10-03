"""claude adapter のテスト。`claude` の代わりに、呼ばれ方を記録する小さなスクリプトを実行する。"""

import json
import logging
import sys
from pathlib import Path

import pytest

from vidcut.adapters.claude_cli import ClaudeCli
from vidcut.pipeline.ports import ExternalToolError, LoginRequiredError

_RECORDER = """\
import json, os, sys
record = {"cwd": os.getcwd(), "argv": sys.argv[1:], "stdin": sys.stdin.read()}
with open(os.environ["FAKE_CLAUDE_RECORD"], "w", encoding="utf-8") as f:
    json.dump(record, f, ensure_ascii=False)
"""


def fake_claude(tmp_path: Path, body: str) -> str:
    """body を実行するスクリプトを作り、そのパスを返す。"""
    script = tmp_path / "fake-claude"
    script.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    script.chmod(0o755)
    return str(script)


@pytest.fixture
def record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(path))
    return path


class TestComplete:
    def test_returns_standard_output(self, tmp_path: Path, record: Path) -> None:
        executable = fake_claude(tmp_path, _RECORDER + "print('{\"delete\": []}')\n")
        cli = ClaudeCli(tmp_path / "ws" / "judge", executable=executable)
        assert cli.complete("指示文\n0\t0.0\t1.0\tこんにちは") == '{"delete": []}\n'

    def test_runs_in_neutral_directory_outside_the_repository(
        self, tmp_path: Path, record: Path
    ) -> None:
        # リポジトリ内で呼ぶと開発用の CLAUDE.md と設定が判定に混ざる（FRIC-002）
        workdir = tmp_path / "ws" / "judge"
        ClaudeCli(workdir, executable=fake_claude(tmp_path, _RECORDER)).complete("p")
        cwd = Path(json.loads(record.read_text(encoding="utf-8"))["cwd"])
        assert cwd.resolve() == workdir.resolve()
        assert workdir.is_dir()
        assert list(workdir.iterdir()) == []

    def test_passes_prompt_on_stdin_not_in_arguments(self, tmp_path: Path, record: Path) -> None:
        prompt = "指示文 $(touch x) ; rm -rf / `id`\n--tools default"
        ClaudeCli(tmp_path / "w", executable=fake_claude(tmp_path, _RECORDER)).complete(prompt)
        recorded = json.loads(record.read_text(encoding="utf-8"))
        assert recorded["stdin"] == prompt
        assert all("指示文" not in arg for arg in recorded["argv"])
        assert not (tmp_path / "w" / "x").exists()

    def test_prints_once_without_tools_or_customizations(
        self, tmp_path: Path, record: Path
    ) -> None:
        ClaudeCli(tmp_path / "w", executable=fake_claude(tmp_path, _RECORDER)).complete("p")
        argv = json.loads(record.read_text(encoding="utf-8"))["argv"]
        assert argv[0] == "-p"
        assert argv[argv.index("--output-format") + 1] == "text"
        assert argv[argv.index("--tools") + 1] == ""  # ツールは 1 つも使わせない
        assert "--safe-mode" in argv  # 利用者の CLAUDE.md・フック・MCP も読み込まない
        assert "--no-session-persistence" in argv

    def test_logs_standard_error(
        self, tmp_path: Path, record: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        body = 'import sys\nprint("warning: slow", file=sys.stderr)\nprint("ok")\n'
        cli = ClaudeCli(tmp_path / "w", executable=fake_claude(tmp_path, body))
        with caplog.at_level(logging.WARNING):
            assert cli.complete("p") == "ok\n"
        assert "warning: slow" in caplog.text


class TestFailures:
    def test_not_logged_in(self, tmp_path: Path) -> None:
        body = 'import sys\nprint("Not logged in · Please run /login")\nsys.exit(1)\n'
        cli = ClaudeCli(tmp_path / "w", executable=fake_claude(tmp_path, body))
        with pytest.raises(LoginRequiredError, match="/login"):
            cli.complete("p")

    def test_invalid_credentials_on_standard_error(self, tmp_path: Path) -> None:
        body = 'import sys\nprint("Invalid API key", file=sys.stderr)\nsys.exit(1)\n'
        cli = ClaudeCli(tmp_path / "w", executable=fake_claude(tmp_path, body))
        with pytest.raises(LoginRequiredError):
            cli.complete("p")

    def test_successful_output_mentioning_login_is_not_an_error(self, tmp_path: Path) -> None:
        body = 'print(\'{"delete": [{"id": 1, "kind": "noise", "reason": "/login と発話"}]}\')\n'
        cli = ClaudeCli(tmp_path / "w", executable=fake_claude(tmp_path, body))
        assert "/login" in cli.complete("p")

    def test_other_failure_reports_exit_code_and_output(self, tmp_path: Path) -> None:
        body = 'import sys\nprint("usage limit reached")\nsys.exit(3)\n'
        cli = ClaudeCli(tmp_path / "w", executable=fake_claude(tmp_path, body))
        with pytest.raises(ExternalToolError, match=r"終了コード 3.*usage limit reached") as info:
            cli.complete("p")
        assert not isinstance(info.value, LoginRequiredError)

    def test_timeout(self, tmp_path: Path) -> None:
        body = "import time\ntime.sleep(30)\n"
        cli = ClaudeCli(tmp_path / "w", executable=fake_claude(tmp_path, body), timeout_s=0.2)
        with pytest.raises(ExternalToolError, match="時間内"):
            cli.complete("p")

    def test_missing_executable(self, tmp_path: Path) -> None:
        cli = ClaudeCli(tmp_path / "w", executable=str(tmp_path / "no-such-claude"))
        with pytest.raises(ExternalToolError, match="見つかりません"):
            cli.complete("p")


@pytest.mark.ml
def test_real_claude_answers_from_neutral_directory(tmp_path: Path) -> None:
    """実物の `claude -p` を呼ぶ（ログイン済みであること）。`uv run pytest -m ml` で実行する。"""
    answer = ClaudeCli(tmp_path / "judge").complete("1+1 の答えを数字だけで答えてください。")
    assert "2" in answer
