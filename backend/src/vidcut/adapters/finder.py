"""書き出したファイルを Finder で選んで見せる（Design Doc 3-5-1 の「Finder で開く」）。"""

import logging
import subprocess
from pathlib import Path

from vidcut.pipeline.ports import RevealFailedError

# PATH を引かない（同じ名前の別のコマンドを実行させない）
_OPEN_COMMAND = "/usr/bin/open"
# Finder で選ぶだけにする。付けないと、フォルダ名が foo.app のときに、アプリとして起動しようとする
_REVEAL_FLAG = "-R"
_TIMEOUT_S = 10.0

_logger = logging.getLogger(__name__)


class FinderRevealer:
    """FileRevealer の実装（macOS）。`/usr/bin/open -R <絶対パス>` を実行する。"""

    def reveal(self, path: Path) -> None:
        # 絶対パスは「/」で始まるので、open のオプションと取り違えられない
        if not path.is_absolute():
            raise ValueError(f"絶対パスではありません: {path}")
        try:
            completed = subprocess.run(
                [_OPEN_COMMAND, _REVEAL_FLAG, str(path)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RevealFailedError(f"open を実行できませんでした: {path}") from e
        if completed.returncode != 0:
            raise RevealFailedError(
                f"open が失敗しました（{completed.returncode}）: {path}: {completed.stderr.strip()}"
            )


class LoggingRevealer:
    """Finder を開かず、見せるはずだった場所をログに出すだけの FileRevealer。

    自動の確認と E2E 用（環境変数 VIDCUT_REVEAL=off。bootstrap.py）。
    """

    def reveal(self, path: Path) -> None:
        _logger.info("Finder で開く（VIDCUT_REVEAL=off のため、開きません）: %s", path)
