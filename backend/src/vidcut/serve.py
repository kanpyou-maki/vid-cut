"""`vidcut serve`: API サーバーと worker プロセスを 1 つずつ起動する（ADR-004、Design Doc 2 章）。

両者は SQLite のジョブ表だけで連携する。サーバーは 127.0.0.1 にだけ待ち受け、
起動のたびにトークンを作って、配信する HTML に埋め込む（Design Doc 3-5-1）。
"""

import logging
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Protocol

import uvicorn
from fastapi import FastAPI

from vidcut.api.app import ApiSettings, create_app
from vidcut.api.security import local_guard, new_token
from vidcut.bootstrap import build_api

HOST = "127.0.0.1"
"""待ち受けるアドレス。ほかの機器から届かないよう、ループバックに固定する。"""
DEFAULT_PORT = 8765
VITE_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
"""開発中の Vite の開発サーバー。--dev のときだけ、ここからの要求を受け付ける。"""
FRONTEND_DIST_ENV = "VIDCUT_FRONTEND_DIST"
WORKSPACE_ENV = "VIDCUT_WORKSPACE"
PARENT_PID_FLAG = "--parent-pid"
_WORKER_STOP_TIMEOUT_S = 10.0
_PARENT_POLL_INTERVAL_S = 1.0

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
    if threading.current_thread() is threading.main_thread():
        interrupt_on_sigterm()
    worker: RunningWorker | None = None
    try:
        if options.with_worker:
            worker = (start_worker or start_worker_process)(options.workspace)
        print(f"http://{HOST}:{options.port}/ を開いてください（Ctrl+C で止めます）")
        print(f"ワークスペース: {options.workspace}")
        (run_server or run_uvicorn)(app, HOST, options.port)
    except KeyboardInterrupt:
        # Ctrl+C と SIGTERM は「止める」合図。エラーにせず、下で worker を止めて終わる
        _logger.info("サーバーを止めます")
    finally:
        if worker is not None:
            worker.stop()
    return 0


def interrupt_on_sigterm() -> None:
    """SIGTERM を Ctrl+C と同じ扱い（KeyboardInterrupt）にする。メインスレッドで呼ぶこと。

    既定の動作のままだと、SIGTERM でプロセスがその場で終わり、後始末（worker の停止）が走らない。
    uvicorn は、止まったあとに受け取ったシグナルを送り直すので、起動の前に設定しておく。
    """

    def interrupt(signum: int, frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)


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


def stop_when_parent_exits(
    stop: threading.Event,
    parent_pid: int,
    *,
    get_parent: Callable[[], int] = os.getppid,
    poll_interval_s: float = _PARENT_POLL_INTERVAL_S,
) -> threading.Thread:
    """親プロセス（parent_pid）がいなくなったら stop を立てる見張りを始める（worker 側で使う）。

    親（vidcut serve）が強制終了されると、後始末が走らず worker だけが残る。
    親がいなくなると、子の親は別のプロセスに変わるので、それを合図に自分で止まる。
    親の番号は起動した側から受け取る。worker の起動（読み込み）の間に親が終わっていると、
    自分で調べた「いまの親」は、もう別のプロセスになっているため。
    処理中のジョブは最後まで行い、次のジョブを取る前に止まる。
    """

    def watch() -> None:
        while True:
            if get_parent() != parent_pid:
                _logger.warning("親プロセスがいなくなったので、worker を止めます")
                stop.set()
            if stop.wait(poll_interval_s):
                return

    watcher = threading.Thread(target=watch, name="parent-watch", daemon=True)
    watcher.start()
    return watcher
