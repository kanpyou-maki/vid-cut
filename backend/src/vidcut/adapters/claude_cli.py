"""LanguageModel の `claude -p` による実装（Design Doc 3-3）。

リポジトリ内で呼ぶと開発用の CLAUDE.md とハーネスの設定が読み込まれ、判定に混ざる（FRIC-002）。
そのため、ワークスペース内の空のディレクトリを作業ディレクトリにし、ツールも利用者の設定も使わせない。
"""

import logging
import subprocess
from pathlib import Path

from vidcut.pipeline.ports import ExternalToolError, LoginRequiredError

DEFAULT_TIMEOUT_S = 600.0
_OUTPUT_TAIL_CHARS = 2000
# 未ログインのとき、claude は「Not logged in · Please run /login」と出して終了コード 1 で終わる
_LOGIN_HINTS = ("/login", "not logged in", "invalid api key")

_logger = logging.getLogger(__name__)


class ClaudeCli:
    """`claude -p` を子プロセスとして 1 回ずつ呼ぶ。"""

    def __init__(
        self, workdir: Path, *, executable: str = "claude", timeout_s: float = DEFAULT_TIMEOUT_S
    ) -> None:
        self._workdir = workdir
        self._executable = executable
        self._timeout_s = timeout_s

    def complete(self, prompt: str) -> str:
        """指示文は標準入力で渡す（引数に入れない）。標準出力だけを結果として返す。"""
        self._workdir.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(
                self._args(),
                input=prompt,
                capture_output=True,
                text=True,
                cwd=self._workdir,
                timeout=self._timeout_s,
            )
        except FileNotFoundError as e:
            raise ExternalToolError(
                f"{self._executable} が見つかりません。Claude Code のインストールを確認してください"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise ExternalToolError(
                f"claude が時間内（{self._timeout_s} 秒）に終わりませんでした"
            ) from e
        if completed.stderr.strip():
            _logger.warning("claude の標準エラー: %s", _tail(completed.stderr))
        if completed.returncode != 0:
            raise _failure(completed)
        return completed.stdout

    def _args(self) -> list[str]:
        return [
            self._executable,
            "-p",
            "--output-format",
            "text",
            "--tools",
            "",  # ツールは 1 つも使わせない
            "--safe-mode",  # 利用者の CLAUDE.md・フック・MCP・スキルを読み込まない
            "--no-session-persistence",
        ]


def _failure(completed: subprocess.CompletedProcess[str]) -> ExternalToolError:
    output = f"{completed.stdout}\n{completed.stderr}"
    if any(hint in output.lower() for hint in _LOGIN_HINTS):
        return LoginRequiredError(
            "claude にログインしていません。"
            "ターミナルで `claude` を起動し、`/login` を実行してください"
        )
    return ExternalToolError(
        f"claude が失敗しました（終了コード {completed.returncode}）: {_tail(output)}"
    )


def _tail(text: str) -> str:
    return text.strip()[-_OUTPUT_TAIL_CHARS:]
