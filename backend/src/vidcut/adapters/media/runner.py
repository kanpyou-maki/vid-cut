"""外部プロセスの実行（引数リスト、タイムアウト、進捗の読み取り）と、生成物の原子的な書き込み。"""

import glob
import os
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from vidcut.pipeline.ports import ExternalToolError, ProgressCallback

_STDERR_TAIL_CHARS = 2000
# これより古い一時ファイルは、強制終了された実行の残りとみなして消す（実行中のものは消さない）
_STALE_PARTIAL_S = 24 * 60 * 60
_PROGRESS_KEY = "out_time_us="


def parse_progress_us(line: str) -> int | None:
    """ffmpeg の -progress の出力 1 行から、出力済みの時刻（マイクロ秒）を読む。"""
    if not line.startswith(_PROGRESS_KEY):
        return None
    value = line[len(_PROGRESS_KEY) :].strip()
    if not value.isdigit():
        return None
    return int(value)


def run_capture(args: list[str], *, timeout_s: float) -> str:
    """短いコマンド（ffprobe）を実行し、標準出力を返す。"""
    try:
        completed = subprocess.run(
            args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout_s
        )
    except FileNotFoundError as e:
        raise _not_found(args[0]) from e
    except subprocess.TimeoutExpired as e:
        raise _timed_out(args[0], timeout_s) from e
    if completed.returncode != 0:
        raise _failure(args[0], completed.returncode, completed.stderr)
    return completed.stdout


def run_with_progress(
    args: list[str],
    *,
    total_ms: int,
    on_progress: ProgressCallback | None,
    timeout_s: float | None = None,
) -> None:
    """ffmpeg を実行し、-progress pipe:1 の出力から進捗（0〜1）を知らせる。成功時は最後に 1.0。"""
    report = on_progress or (lambda _: None)
    with tempfile.TemporaryFile(mode="w+") as stderr:
        try:
            process = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr, text=True
            )
        except FileNotFoundError as e:
            raise _not_found(args[0]) from e
        timed_out = threading.Event()
        timer = _kill_after(process, timeout_s, timed_out)
        try:
            _follow_progress(process, total_ms, report)
            returncode = process.wait()
        except BaseException:
            # 呼び出し側の例外や中断で ffmpeg が孤児として書き続けないよう止める
            process.kill()
            process.wait()
            raise
        finally:
            if timer is not None:
                timer.cancel()
        if timed_out.is_set():
            raise _timed_out(args[0], timeout_s)
        if returncode != 0:
            stderr.seek(0)
            raise _failure(args[0], returncode, stderr.read())
    report(1.0)


def write_atomically(dest: Path, produce: Callable[[Path], None]) -> None:
    """produce に一時ファイルへ書かせ、成功したときだけ dest に置く。

    途中で止まった生成物を完成品と誤認しないため（段の再開は生成物の有無で判断する）。
    一時ファイルの名前は呼び出しごとに変える（同じ生成物を同時に作っても、互いの書きかけを壊さない）。
    拡張子は dest と同じにする（ffmpeg は拡張子で形式を決める）。
    強制終了されると一時ファイルが残るので、同じ生成物の古い一時ファイルを先に片付ける。
    """
    _remove_stale_partials(dest)
    partial = dest.with_name(f".{dest.stem}.{uuid.uuid4().hex[:8]}.partial{dest.suffix}")
    try:
        produce(partial)
        if not partial.exists():
            raise ExternalToolError(f"出力ファイルが作られませんでした: {dest.name}")
        os.replace(partial, dest)
    finally:
        partial.unlink(missing_ok=True)


def _remove_stale_partials(dest: Path) -> None:
    oldest_kept = time.time() - _STALE_PARTIAL_S
    for leftover in dest.parent.glob(f".{glob.escape(dest.stem)}.*.partial{dest.suffix}"):
        try:
            if leftover.stat().st_mtime < oldest_kept:
                leftover.unlink()
        except OSError:
            # 別の実行が先に片付けた、など。片付けは後回しにできるので、本来の処理を止めない
            continue


def _follow_progress(
    process: subprocess.Popen[str], total_ms: int, report: ProgressCallback
) -> None:
    assert process.stdout is not None
    total_us = max(total_ms, 1) * 1000
    for line in process.stdout:
        out_us = parse_progress_us(line)
        if out_us is not None:
            report(min(out_us / total_us, 1.0))


def _kill_after(
    process: subprocess.Popen[str], timeout_s: float | None, timed_out: threading.Event
) -> threading.Timer | None:
    if timeout_s is None:
        return None

    def kill() -> None:
        timed_out.set()
        process.kill()

    timer = threading.Timer(timeout_s, kill)
    timer.daemon = True
    timer.start()
    return timer


def _failure(program: str, returncode: int, stderr: str) -> ExternalToolError:
    tail = stderr.strip()[-_STDERR_TAIL_CHARS:]
    return ExternalToolError(f"{program} が失敗しました（終了コード {returncode}）: {tail}")


def _not_found(program: str) -> ExternalToolError:
    return ExternalToolError(f"{program} が見つかりません。インストールを確認してください")


def _timed_out(program: str, timeout_s: float | None) -> ExternalToolError:
    return ExternalToolError(f"{program} が時間内（{timeout_s} 秒）に終わりませんでした")
