"""E2E 用の `vidcut serve`: 専用のフォルダで、偽の ML・偽の判定の worker と一緒に起動する。

    uv run --directory backend python -m tests.e2e.serve --root <フォルダ> --port <ポート> \\
        --frontend-dist <ビルドの出力>

--root は、実行のたびに消して作り直す（stage.py。このスクリプトが作ったフォルダだけ）。
ワークスペースは <root>/workspace に固定で、環境変数 VIDCUT_WORKSPACE は見ない
（実データを使わない）。
"""

import argparse
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from tests.e2e.material import make_lesson as make_real_lesson
from tests.e2e.stage import LessonMaker, prepare
from vidcut.bootstrap import REVEAL_ENV, REVEAL_OFF
from vidcut.process import PARENT_PID_FLAG
from vidcut.serve import WORKSPACE_ENV, ServeOptions, WorkerProcess
from vidcut.serve import serve as real_serve

BACKEND_ROOT = Path(__file__).resolve().parents[2]

ServeFunction = Callable[..., int]


def start_fake_worker(workspace: Path) -> WorkerProcess:
    """`vidcut worker` の代わりに、偽の実装で組み立てた worker（worker.py）を起動する。

    本物と同じく、このプロセスがいなくなったら止まる。
    """
    process = subprocess.Popen(
        [sys.executable, "-m", "tests.e2e.worker", PARENT_PID_FLAG, str(os.getpid())],
        stdin=subprocess.DEVNULL,
        cwd=BACKEND_ROOT,
        env={**os.environ, WORKSPACE_ENV: str(workspace)},
    )
    return WorkerProcess(process)


def main(
    argv: Sequence[str] | None = None,
    *,
    serve: ServeFunction = real_serve,
    make_lesson: LessonMaker = make_real_lesson,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--frontend-dist", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # 「Finder で開く」は、ログに出すだけにする（worker にも引き継がれる）
    os.environ[REVEAL_ENV] = REVEAL_OFF
    stage = prepare(args.root, make_lesson=make_lesson)
    options = ServeOptions(
        workspace=stage.workspace,
        home=stage.home,
        frontend_dist=args.frontend_dist,
        port=args.port,
    )
    return serve(options, start_worker=start_fake_worker)


if __name__ == "__main__":
    sys.exit(main())
