import logging
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.domain.models import ErrorCode, Job, JobKind, JobStatus
from vidcut.jobs.worker import MAX_ERROR_CHARS, JobHandler, Worker
from vidcut.pipeline.ports import ExternalToolError, LoginRequiredError, ProgressReporter


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "vidcut.sqlite3"


@pytest.fixture
def queue(db_path: Path) -> Iterator[SqliteJobQueue]:
    conn = open_database(db_path)
    yield SqliteJobQueue(conn)
    conn.close()


def enqueue(queue: SqliteJobQueue, jid: str, kind: JobKind = JobKind.ANALYZE_RECORDING) -> None:
    queue.enqueue(Job(id=jid, kind=kind, target_id=f"t-{jid}"))


def status_of(queue: SqliteJobQueue, jid: str) -> JobStatus:
    stored = queue.get(jid)
    assert stored is not None
    return stored.job.status


def error_of(queue: SqliteJobQueue, jid: str) -> str | None:
    stored = queue.get(jid)
    assert stored is not None
    return stored.job.error


class Recorder:
    """呼ばれたジョブを記録する偽の処理。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, job: Job, report: ProgressReporter) -> None:
        self.calls.append(job.id)


def error_code_of(queue: SqliteJobQueue, jid: str) -> ErrorCode | None:
    stored = queue.get(jid)
    assert stored is not None
    return stored.job.error_code


def failing(message: str, error_type: type[Exception] = RuntimeError) -> JobHandler:
    def handler(job: Job, report: ProgressReporter) -> None:
        raise error_type(message)

    return handler


class TestRunOnce:
    def test_returns_none_when_idle(self, queue: SqliteJobQueue) -> None:
        assert Worker(queue, {}).run_once() is None

    def test_runs_handler_and_marks_success(self, queue: SqliteJobQueue) -> None:
        enqueue(queue, "j1")
        handler = Recorder()
        processed = Worker(queue, {JobKind.ANALYZE_RECORDING: handler}).run_once()
        assert processed is not None
        assert processed.id == "j1"
        assert handler.calls == ["j1"]
        assert status_of(queue, "j1") is JobStatus.SUCCEEDED

    def test_handler_reports_stage_and_progress(self, queue: SqliteJobQueue) -> None:
        enqueue(queue, "j1")
        seen: list[tuple[str | None, float]] = []

        def handler(job: Job, report: ProgressReporter) -> None:
            report("transcribe", 0.5)
            stored = queue.get(job.id)
            assert stored is not None
            seen.append((stored.job.stage, stored.job.progress))

        Worker(queue, {JobKind.ANALYZE_RECORDING: handler}).run_once()
        assert seen == [("transcribe", 0.5)]

    def test_logs_start_and_each_new_stage(
        self, queue: SqliteJobQueue, caplog: pytest.LogCaptureFixture
    ) -> None:
        enqueue(queue, "j1")

        def handler(job: Job, report: ProgressReporter) -> None:
            report("transcribe", 0.1)
            report("transcribe", 0.2)
            report("align", 0.8)

        with caplog.at_level(logging.INFO):
            Worker(queue, {JobKind.ANALYZE_RECORDING: handler}).run_once()
        messages = [r.getMessage() for r in caplog.records]
        assert any("j1" in m and "開始" in m for m in messages)
        assert sum("transcribe" in m for m in messages) == 1
        assert any("align" in m for m in messages)

    def test_failure_is_recorded_and_logged(
        self, queue: SqliteJobQueue, caplog: pytest.LogCaptureFixture
    ) -> None:
        enqueue(queue, "j1")
        worker = Worker(queue, {JobKind.ANALYZE_RECORDING: failing("ffmpeg が失敗しました")})
        with caplog.at_level(logging.ERROR):
            worker.run_once()
        assert status_of(queue, "j1") is JobStatus.FAILED
        assert error_of(queue, "j1") == "ffmpeg が失敗しました"
        assert "j1" in caplog.text

    @pytest.mark.parametrize(
        ("error_type", "code"),
        [
            (LoginRequiredError, ErrorCode.LOGIN_REQUIRED),
            (ExternalToolError, ErrorCode.TOOL_FAILED),
            (FileNotFoundError, ErrorCode.SOURCE_MISSING),
            (RuntimeError, ErrorCode.INTERNAL),
        ],
    )
    def test_failure_is_sorted_into_an_error_code(
        self, queue: SqliteJobQueue, error_type: type[Exception], code: ErrorCode
    ) -> None:
        enqueue(queue, "j1")
        handler = failing("/Users/me/a.mov を処理できません", error_type)
        Worker(queue, {JobKind.ANALYZE_RECORDING: handler}).run_once()
        assert error_code_of(queue, "j1") is code

    def test_long_error_is_truncated(self, queue: SqliteJobQueue) -> None:
        enqueue(queue, "j1")
        Worker(queue, {JobKind.ANALYZE_RECORDING: failing("x" * 5000)}).run_once()
        error = error_of(queue, "j1")
        assert error is not None
        assert len(error) == MAX_ERROR_CHARS

    def test_error_without_message_uses_exception_name(self, queue: SqliteJobQueue) -> None:
        enqueue(queue, "j1")

        def handler(job: Job, report: ProgressReporter) -> None:
            raise TimeoutError

        Worker(queue, {JobKind.ANALYZE_RECORDING: handler}).run_once()
        assert error_of(queue, "j1") == "TimeoutError"

    def test_job_without_handler_fails(self, queue: SqliteJobQueue) -> None:
        enqueue(queue, "j1", JobKind.EXPORT_MP4)
        Worker(queue, {}).run_once()
        assert status_of(queue, "j1") is JobStatus.FAILED
        assert "export_mp4" in (error_of(queue, "j1") or "")
        assert error_code_of(queue, "j1") is ErrorCode.INTERNAL

    def test_interrupt_leaves_job_running_for_recovery(self, queue: SqliteJobQueue) -> None:
        enqueue(queue, "j1")

        def handler(job: Job, report: ProgressReporter) -> None:
            raise KeyboardInterrupt

        worker = Worker(queue, {JobKind.ANALYZE_RECORDING: handler})
        with pytest.raises(KeyboardInterrupt):
            worker.run_once()
        assert status_of(queue, "j1") is JobStatus.RUNNING
        assert worker.recover() == 1
        assert status_of(queue, "j1") is JobStatus.QUEUED


class TestRunUntilIdle:
    def test_processes_everything_in_priority_order(self, queue: SqliteJobQueue) -> None:
        enqueue(queue, "mezz", JobKind.MAKE_MEZZANINE)
        enqueue(queue, "a1")
        enqueue(queue, "bad")
        enqueue(queue, "a2")
        handler = Recorder()

        def dispatch(job: Job, report: ProgressReporter) -> None:
            handler(job, report)
            if job.id == "bad":
                raise ValueError("broken input")

        worker = Worker(
            queue, {JobKind.ANALYZE_RECORDING: dispatch, JobKind.MAKE_MEZZANINE: handler}
        )
        assert worker.run_until_idle() == 4
        assert handler.calls == ["a1", "bad", "a2", "mezz"]
        assert status_of(queue, "a2") is JobStatus.SUCCEEDED
        assert status_of(queue, "bad") is JobStatus.FAILED


class TestRunForever:
    def test_recovers_then_processes_until_stopped(self, queue: SqliteJobQueue) -> None:
        enqueue(queue, "crashed")
        queue.claim_next()  # 前回の worker が処理中に落ちた
        enqueue(queue, "next")
        stop = threading.Event()
        handler = Recorder()

        def run_and_stop(job: Job, report: ProgressReporter) -> None:
            handler(job, report)
            if job.id == "next":
                stop.set()

        Worker(queue, {JobKind.ANALYZE_RECORDING: run_and_stop}).run_forever(
            stop, poll_interval_s=0.01
        )
        assert handler.calls == ["crashed", "next"]

    def test_keeps_running_when_recording_a_result_fails(
        self, queue: SqliteJobQueue, db_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        enqueue(queue, "vanishing")
        enqueue(queue, "next")
        stop = threading.Event()
        handler = Recorder()
        other = open_database(db_path)

        def run(job: Job, report: ProgressReporter) -> None:
            handler(job, report)
            if job.id == "vanishing":
                other.execute("DELETE FROM jobs WHERE id = 'vanishing'")  # 結果を書けなくなる
            else:
                stop.set()

        with caplog.at_level(logging.ERROR):
            Worker(queue, {JobKind.ANALYZE_RECORDING: run}).run_forever(stop, poll_interval_s=0.01)
        other.close()
        assert handler.calls == ["vanishing", "next"]
        assert "vanishing" in caplog.text

    def test_waits_for_new_jobs_while_idle(self, queue: SqliteJobQueue, db_path: Path) -> None:
        stop = threading.Event()
        handler = Recorder()

        def run_and_stop(job: Job, report: ProgressReporter) -> None:
            handler(job, report)
            stop.set()

        def run_worker() -> None:
            # worker は別プロセス・別スレッドで動くので、自分の接続を持つ
            conn = open_database(db_path)
            worker = Worker(SqliteJobQueue(conn), {JobKind.ANALYZE_RECORDING: run_and_stop})
            worker.run_forever(stop, poll_interval_s=0.01)
            conn.close()

        thread = threading.Thread(target=run_worker)
        thread.start()
        enqueue(queue, "late")
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert handler.calls == ["late"]
