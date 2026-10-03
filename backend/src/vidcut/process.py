"""プロセスの止め方: 止める合図の扱いと、親プロセスの見張り。

`vidcut serve` と `vidcut worker` が使う。
"""

import logging
import os
import signal
import threading
from collections.abc import Callable
from types import FrameType

PARENT_PID_FLAG = "--parent-pid"
"""`vidcut worker` の引数。`vidcut serve` が自分のプロセス番号を渡す。"""
_PARENT_POLL_INTERVAL_S = 1.0

_logger = logging.getLogger(__name__)


def interrupt_on_sigterm() -> None:
    """SIGTERM を Ctrl+C と同じ扱い（KeyboardInterrupt）にする。

    既定の動作のままだと、SIGTERM でプロセスがその場で終わり、後始末（worker の停止）が走らない。
    uvicorn は、止まったあとに受け取ったシグナルを送り直すので、起動の前に設定しておく。
    シグナルの扱いはメインスレッドでしか変えられないので、ほかのスレッドから呼ばれたら何もしない。
    """
    if threading.current_thread() is not threading.main_thread():
        return

    def interrupt(signum: int, frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)


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
