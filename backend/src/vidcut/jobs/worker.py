"""ジョブを 1 件ずつ取り出して処理する worker のループ（Design Doc 2 章、ADR-004）。"""

import logging
import threading
from collections.abc import Callable, Mapping

from vidcut.domain.models import Job, JobKind
from vidcut.pipeline.ports import JobQueue, ProgressReporter

MAX_ERROR_CHARS = 1000
"""画面に出すエラーの最大文字数。詳細はログに残す。"""

JobHandler = Callable[[Job, ProgressReporter], None]

_logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        queue: JobQueue,
        handlers: Mapping[JobKind, JobHandler],
        *,
        logger: logging.Logger = _logger,
    ) -> None:
        self._queue = queue
        self._handlers = dict(handlers)
        self._logger = logger

    def recover(self) -> int:
        """前回の worker が処理中に止まったジョブを待機中に戻す。各段は生成物から再開する。"""
        count = self._queue.requeue_running()
        if count:
            self._logger.info("処理中のまま残っていたジョブ %d 件を待機中に戻しました", count)
        return count

    def run_once(self) -> Job | None:
        """待機中のジョブを 1 件処理し、そのジョブを返す。なければ None。

        処理中の例外は失敗として記録する。KeyboardInterrupt などは記録せずに伝え、
        ジョブは実行中のまま残る（次の起動時に recover() で戻す）。
        """
        job = self._queue.claim_next()
        if job is None:
            return None
        handler = self._handlers.get(job.kind)
        try:
            if handler is None:
                raise LookupError(f"{job.kind} の処理方法がありません")
            handler(
                job, lambda stage, progress: self._queue.report_progress(job.id, stage, progress)
            )
        except Exception as e:
            self._logger.exception("ジョブ %s（%s）が失敗しました", job.id, job.kind)
            self._queue.mark_failed(job.id, _error_message(e))
        else:
            self._queue.mark_succeeded(job.id)
        return job

    def run_until_idle(self) -> int:
        """待機中のジョブがなくなるまで処理し、処理した件数を返す（`vidcut analyze --wait`）。"""
        count = 0
        while self.run_once() is not None:
            count += 1
        return count

    def run_forever(self, stop: threading.Event, *, poll_interval_s: float = 1.0) -> None:
        """stop が立つまで、ジョブを待って処理し続ける（`vidcut serve` / `vidcut worker`）。"""
        self.recover()
        while not stop.is_set():
            try:
                processed = self.run_once()
            except Exception:
                # 結果の記録に失敗しても（ジョブが消された・DB が使えない）、worker は止めない
                self._logger.exception("ジョブの処理結果を記録できませんでした")
                processed = None
            if processed is None:
                stop.wait(poll_interval_s)


def _error_message(error: Exception) -> str:
    return (str(error) or type(error).__name__)[:MAX_ERROR_CHARS]
