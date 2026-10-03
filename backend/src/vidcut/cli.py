"""コマンドライン: vidcut analyze / worker / eval judge（Design Doc 2 章・6 章）。"""

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
from vidcut.pipeline.judge import JudgeEntry
from vidcut.pipeline.ports import ExternalToolError
from vidcut.services.imports import ImportResult
from vidcut.services.judge_eval import (
    PRECISION_TARGET,
    RECALL_TARGET,
    EvalRun,
    load_sample_entries,
    load_truth,
)

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
        if args.command == "eval":
            return _eval_judge(app, args)
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
    evaluations = commands.add_parser("eval", help="精度を評価する").add_subparsers(
        dest="target", required=True
    )
    judge = evaluations.add_parser(
        "judge", help="言い直しの判定を正解データと比べる（claude を呼ぶ）"
    )
    source = judge.add_mutually_exclusive_group(required=True)
    source.add_argument("--chunks", type=Path, help="チャンク一覧の JSON（プロトタイプの形）")
    source.add_argument("--lecture", help="解析済みのレクチャーの題名または id")
    judge.add_argument("--truth", type=Path, required=True, help="正解データの JSON")
    judge.add_argument("--runs", type=_positive_int, default=1, help="判定を繰り返す回数")
    return parser


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("1 以上を指定してください")
    return number


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
    for failure in result.failed:
        print(f"  失敗 {failure.path}: {failure.message}")


def _eval_judge(app: App, args: argparse.Namespace) -> int:
    """終了コード 0: すべての回で目標（適合率 90%・再現率 80%）を達成。"""
    try:
        truth = load_truth(args.truth)
        if args.chunks is not None:
            entries = load_sample_entries(args.chunks)
        else:
            entries = app.judge_eval.lecture_entries(args.lecture)
        print(f"{len(entries)} チャンクを判定します（正解の削除対象: {len(truth)} 件）")
        runs: list[EvalRun] = []
        for index in range(args.runs):
            run = app.judge_eval.run(entries, truth)
            _print_eval_run(index + 1, run, entries)
            runs.append(run)
    except (ExternalToolError, LookupError, ValueError) as e:
        print(f"評価できませんでした: {e}")
        return 1
    achieved = all(run.score.meets_targets for run in runs)
    print(
        f"結果: 目標（適合率 {PRECISION_TARGET:.0%} 以上・再現率 {RECALL_TARGET:.0%} 以上）"
        f"{'を達成' if achieved else 'は未達'}"
    )
    return 0 if achieved else 1


def _print_eval_run(index: int, run: EvalRun, entries: Sequence[JudgeEntry]) -> None:
    score = run.score
    deleted = len(score.correct) + len(score.wrong)
    expected = len(score.correct) + len(score.missed)
    print(
        f"{index} 回目: 適合率 {score.precision:.1%}（{len(score.correct)}/{deleted}）"
        f" 再現率 {score.recall:.1%}（{len(score.correct)}/{expected}）"
    )
    texts = {entry.number: entry.text for entry in entries}
    decisions = {decision.number: decision for decision in run.decisions}
    for number in score.wrong:
        decision = decisions[number]
        print(f"  誤って削除 {number} {texts[number]}（{decision.kind}: {decision.reason}）")
    for number in score.missed:
        print(f"  見逃し {number} {texts[number]}")


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
