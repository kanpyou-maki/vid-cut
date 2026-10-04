"""`vidcut serve`: API サーバーと worker プロセスを 1 つずつ起動する（ADR-004、Design Doc 2 章）。

両者は SQLite のジョブ表だけで連携する。サーバーは 127.0.0.1 にだけ待ち受け、
起動のたびにトークンを作って、配信する HTML に埋め込む（Design Doc 3-5-1）。
"""

import logging
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import uvicorn
from fastapi import FastAPI

from vidcut.api.app import ApiSettings, create_app
from vidcut.api.security import local_guard, new_token
from vidcut.bootstrap import build_api
from vidcut.process import PARENT_PID_FLAG, interrupt_on_sigterm

HOST = "127.0.0.1"
"""待ち受けるアドレス。ほかの機器から届かないよう、ループバックに固定する。"""
DEFAULT_PORT = 8765
VITE_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
"""開発中の Vite の開発サーバー。--dev のときだけ、ここからの要求を受け付ける。"""
FRONTEND_DIST_ENV = "VIDCUT_FRONTEND_DIST"
WORKSPACE_ENV = "VIDCUT_WORKSPACE"
_WORKER_STOP_TIMEOUT_S = 10.0
# frontend のテストの置き方（frontend/README.md）。ビルドの出力には入らない
_FRONTEND_TEST_DIRECTORY = "test"
_FRONTEND_TEST_INFIX = ".test."
STALE_BUILD_NOTE = (
    "注意: 画面のビルドが、ソースより古いようです（新しい画面が出ません）。"
    "`npm --prefix frontend run build` を実行してから、起動し直してください"
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServeOptions:
    workspace: Path
    home: Path  # /api/fs と /api/imports が見せてよい範囲
    frontend_dist: Path | None
    port: int = DEFAULT_PORT
    dev: bool = False  # Vite の開発サーバーからの要求を受け付ける
    with_worker: bool = True


class RunningWorker(Protocol):
    def stop(self) -> None: ...


ServerRunner = Callable[[FastAPI, str, int], None]
"""アプリを host:port で動かし、止まるまで戻らない。"""
WorkerStarter = Callable[[Path], RunningWorker]
"""ワークスペースのジョブを処理する worker を起動する。"""


def default_frontend_dist(env: Mapping[str, str] = os.environ) -> Path:
    """ビルド済み frontend の場所。既定はこのリポジトリの frontend/dist。

    既定の場所は、リポジトリの中で動かしていること（backend/src/vidcut/ にこのファイルがあること）が
    前提。ほかの場所に導入したときは、環境変数で指定する（なければ、ビルドの案内のページを返す）。
    """
    configured = env.get(FRONTEND_DIST_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


def frontend_build_is_stale(dist: Path | None) -> bool:
    """ビルドの出力（dist）が、隣にある画面のソース（src）より古いか。

    ビルドし直さないと、古い画面を配信し続ける（backend だけが新しくなり、画面の機能が出ない）。
    ビルドがない・ソースが隣にない（リポジトリの外に置いたビルド）ときは、比べようがないので False。
    テストとその補助は、ビルドの出力に入らないので見ない。目安であって、確かではない:
    src の外（index.html・package.json・vite.config.ts・public/）の変更は見ない。
    ブランチを切り替えただけで更新時刻が変わったファイルは、古いと見なす。
    """
    if dist is None:
        return False
    index = dist / "index.html"
    sources = dist.parent / "src"
    try:
        if not index.is_file() or not sources.is_dir():
            return False
        built_at = index.stat().st_mtime
        return any(
            path.stat().st_mtime > built_at
            for path in sources.rglob("*")
            if path.is_file() and not _is_test_source(path.relative_to(sources))
        )
    except OSError as error:
        # 知らせるための確認なので、読めないファイルがあっても起動を止めない
        _logger.warning("画面のビルドが古いかどうかを、確かめられませんでした: %s", error)
        return False


def _is_test_source(relative: Path) -> bool:
    """frontend/src からの相対パスが、テストかその補助か（src/test/ の中か、名前に .test.）。"""
    return relative.parts[0] == _FRONTEND_TEST_DIRECTORY or _FRONTEND_TEST_INFIX in relative.name


def serve(
    options: ServeOptions,
    *,
    run_server: ServerRunner | None = None,
    start_worker: WorkerStarter | None = None,
) -> int:
    """サーバーが止まるまで動かす。worker は、サーバーがどう終わっても止める。"""
    api = build_api(options.workspace)
    # トークンは起動ごとに作る。環境変数にも、引数にも、ログにも出さない（worker にも渡さない）
    guard = local_guard(
        new_token(), port=options.port, dev_origins=VITE_ORIGINS if options.dev else ()
    )
    app = create_app(
        api, ApiSettings(guard=guard, home=options.home, frontend_dist=options.frontend_dist)
    )
    # worker を起動する前に設定する。既定の動作のままだと、SIGTERM でこのプロセスがその場で終わり、
    # 下の後始末（worker の停止）が走らない
    interrupt_on_sigterm()
    worker: RunningWorker | None = None
    try:
        if options.with_worker:
            worker = (start_worker or start_worker_process)(options.workspace)
        print(f"http://{HOST}:{options.port}/ を開いてください（Ctrl+C で止めます）")
        print(f"ワークスペース: {options.workspace}")
        # 開発中は Vite が画面を配信するので、ビルドは使わない
        if not options.dev and frontend_build_is_stale(options.frontend_dist):
            print(STALE_BUILD_NOTE)
        (run_server or run_uvicorn)(app, HOST, options.port)
    except KeyboardInterrupt:
        # Ctrl+C と SIGTERM は「止める」合図。エラーにせず、下で worker を止めて終わる
        _logger.info("サーバーを止めます")
    finally:
        if worker is not None:
            worker.stop()
    return 0


def run_uvicorn(app: FastAPI, host: str, port: int) -> None:
    """アクセスログは出さない（proxy 動画の URL には ?token= が付く）。失敗はアプリがログに出す。"""
    uvicorn.run(app, host=host, port=port, access_log=False, log_level="info")


class WorkerProcess:
    """`vidcut worker` の子プロセス。"""

    def __init__(
        self, process: subprocess.Popen[bytes], *, stop_timeout_s: float = _WORKER_STOP_TIMEOUT_S
    ) -> None:
        self._process = process
        self._stop_timeout_s = stop_timeout_s

    def stop(self) -> None:
        """SIGTERM で止める。処理中のジョブは、次の起動時に待機中へ戻る。"""
        if self._process.poll() is not None:
            _logger.warning(
                "worker は既に終了していました（終了コード %s）", self._process.returncode
            )
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=self._stop_timeout_s)
        except subprocess.TimeoutExpired:
            _logger.warning("worker が止まらないため、強制終了します")
            self._process.kill()
            self._process.wait()


def start_worker_process(workspace: Path) -> WorkerProcess:
    """同じ Python で `vidcut worker` を起動する。ワークスペースは環境変数で渡す。

    このプロセスが強制終了されても worker が残らないよう、親がいなくなったら止まるように起動する。
    """
    process = subprocess.Popen(
        [sys.executable, "-m", "vidcut.cli", "worker", PARENT_PID_FLAG, str(os.getpid())],
        stdin=subprocess.DEVNULL,
        env={**os.environ, WORKSPACE_ENV: str(workspace)},
    )
    return WorkerProcess(process)
