"""E2E 用の `vidcut worker`: ML と判定だけを偽の実装に差し替えて、ジョブを処理する。

serve.py が子プロセスとして起動する。止め方と親の見張りは、本物の worker と同じ。
"""

import sys
from collections.abc import Callable, Sequence

from tests.e2e.stage import fake_app
from vidcut import cli
from vidcut.bootstrap import workspace_from_env

RunCli = Callable[..., int]


def main(argv: Sequence[str] | None = None, *, run: RunCli = cli.main) -> int:
    args = sys.argv[1:] if argv is None else argv
    return run(["worker", *args], build=lambda: fake_app(workspace_from_env()))


if __name__ == "__main__":
    sys.exit(main())
