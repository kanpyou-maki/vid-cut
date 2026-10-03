"""コマンドライン: vidcut analyze <paths...> [--wait] / vidcut worker（Design Doc 2 章）。"""

import argparse
import logging
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FrameType

from vidcut.bootstrap import App, build_app, workspace_from_env
from vidcut.domain.models import JobStatus
from vidcut.services.imports import ImportResult

AppFactory = Callable[[], App]


def main(
    argv: Sequence[str] | None = None,
    *,
    build: AppFactory | None = None,
    stop: threading.Event | None = None,
) -> int:
    """終了コードを返す（0: 成功、1: 失敗したファイルやジョブがある）。"""
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = (build or (lambda: build_app(workspace_from_env())))()
    try:
        if args.command == "analyze":
            return _analyze(app, [Path(p) for p in args.paths], wait=args.wait)
        return _worker(app, stop or threading.Event())
    finally:
        app.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vidcut", description="講座録画のカット編集")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="録画ファイル（またはフォルダ）を解析に回す")
    analyze.add_argument("paths", nargs="+", help="録画ファイルまたはフォルダ")
    analyze.add_argument("--wait", action="store_true", help="この場で解析が終わるまで処理する")
    commands.add_parser("worker", help="ジョブを待って処理し続ける")
    return parser


def _analyze(app: App, paths: list[Path], *, wait: bool) -> int:
    result = app.imports.import_paths(paths)
    _print_import(result)
    if not wait:
        print("解析は `vidcut worker`（または `vidcut serve`）が順に実行します")
        return 1 if result.failed else 0
    worker = app.worker()
    processed = []
    while (job := worker.run_once()) is not None:
        processed.append(job.id)
    stored = [app.queue.get(job_id) for job_id in processed]
    failed = [s for s in stored if s is not None and s.job.status is JobStatus.FAILED]
    print(f"ジョブ 成功: {len(processed) - len(failed)} 件 / 失敗: {len(failed)} 件")
    for s in failed:
        print(f"  失敗 {s.job.kind}（{s.job.target_id}）: {s.job.error}")
    return 1 if result.failed or failed else 0


def _print_import(result: ImportResult) -> None:
    print(
        f"登録: {len(result.added)} 本 / 登録済み: {len(result.existing)} 本"
        f" / 失敗: {len(result.failed)} 本"
    )
    for recording in result.added:
        print(f"  登録 {recording.source_path}")
    for path, message in result.failed:
        print(f"  失敗 {path}: {message}")


def _worker(app: App, stop: threading.Event) -> int:
    def interrupt(signum: int, frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    # SIGTERM でも Ctrl+C と同じく止める。処理中のジョブは次の起動時に待機中へ戻る
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, interrupt)
    print(f"ジョブを待っています（ワークスペース: {app.workspace}）。Ctrl+C で止めます")
    try:
        app.worker().run_forever(stop)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
