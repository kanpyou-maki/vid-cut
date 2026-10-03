import os
import sys
import time
from pathlib import Path

import pytest

from vidcut.adapters.media.runner import (
    parse_progress_us,
    run_capture,
    run_with_progress,
    write_atomically,
)
from vidcut.adapters.media.tool import FfmpegMediaTool
from vidcut.pipeline.ports import ExternalToolError, UnsupportedMediaError


def python_args(code: str) -> list[str]:
    """ffmpeg の代わりに、決まった出力をする Python を実行する。"""
    return [sys.executable, "-c", code]


class TestParseProgress:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("out_time_us=1500000", 1_500_000),
            ("out_time_us=1500000\n", 1_500_000),
            ("out_time_us=N/A", None),
            ("out_time_us=-9223372036854775807", None),
            ("frame=12", None),
            ("progress=end", None),
        ],
    )
    def test_reads_output_time_in_microseconds(self, line: str, expected: int | None) -> None:
        assert parse_progress_us(line) == expected


class TestRunWithProgress:
    def test_reports_fraction_of_total_duration(self) -> None:
        code = "print('out_time_us=500000'); print('out_time_us=1000000'); print('progress=end')"
        reported: list[float] = []
        run_with_progress(python_args(code), total_ms=2_000, on_progress=reported.append)
        assert reported == [0.25, 0.5, 1.0]

    def test_clamps_progress_beyond_total(self) -> None:
        reported: list[float] = []
        code = "print('out_time_us=9000000')"
        run_with_progress(python_args(code), total_ms=1_000, on_progress=reported.append)
        assert reported == [1.0, 1.0]

    def test_works_without_progress_callback(self) -> None:
        run_with_progress(python_args("print('out_time_us=1')"), total_ms=1, on_progress=None)

    def test_failure_includes_stderr_tail(self) -> None:
        code = "import sys; sys.stderr.write('Invalid data found\\n'); sys.exit(1)"
        with pytest.raises(ExternalToolError, match="Invalid data found"):
            run_with_progress(python_args(code), total_ms=1_000, on_progress=None)

    def test_missing_program_is_reported_by_name(self) -> None:
        with pytest.raises(ExternalToolError, match="no-such-ffmpeg"):
            run_with_progress(["no-such-ffmpeg", "-i", "/x"], total_ms=1, on_progress=None)

    def test_kills_process_after_timeout(self) -> None:
        with pytest.raises(ExternalToolError, match="時間内"):
            run_with_progress(
                python_args("import time; time.sleep(5)"),
                total_ms=1,
                on_progress=None,
                timeout_s=0.2,
            )

    def test_kills_process_when_progress_callback_fails(self, tmp_path: Path) -> None:
        # worker の中断などで呼び出し側が例外を出したら、ffmpeg を残さない
        pid_file = tmp_path / "pid"
        code = (
            f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); "
            "print('out_time_us=1', flush=True); time.sleep(30)"
        )

        def explode(_: float) -> None:
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            run_with_progress(python_args(code), total_ms=1_000, on_progress=explode)
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)


class TestRunCapture:
    def test_returns_stdout(self) -> None:
        assert run_capture(python_args("print('{}')"), timeout_s=10).strip() == "{}"

    def test_failure_includes_stderr(self) -> None:
        code = "import sys; sys.stderr.write('No such file'); sys.exit(1)"
        with pytest.raises(ExternalToolError, match="No such file"):
            run_capture(python_args(code), timeout_s=10)

    def test_missing_program(self) -> None:
        with pytest.raises(ExternalToolError, match="no-such-ffprobe"):
            run_capture(["no-such-ffprobe"], timeout_s=10)

    def test_timeout(self) -> None:
        with pytest.raises(ExternalToolError, match="時間内"):
            run_capture(python_args("import time; time.sleep(5)"), timeout_s=0.2)


class TestWriteAtomically:
    def test_moves_completed_output_into_place(self, tmp_path: Path) -> None:
        dest = tmp_path / "proxy.mp4"
        seen: list[Path] = []

        def produce(partial: Path) -> None:
            seen.append(partial)
            partial.write_bytes(b"data")

        write_atomically(dest, produce)
        assert dest.read_bytes() == b"data"
        assert seen[0] != dest
        assert seen[0].suffix == ".mp4"  # ffmpeg は拡張子で形式を決める
        assert not seen[0].exists()

    def test_each_call_writes_to_its_own_temporary_file(self, tmp_path: Path) -> None:
        # 2 つの worker が同じ生成物を同時に作っても、互いの書きかけを壊さない
        seen: list[Path] = []

        def produce(partial: Path) -> None:
            seen.append(partial)
            partial.write_bytes(b"data")

        write_atomically(tmp_path / "mezzanine.mp4", produce)
        write_atomically(tmp_path / "mezzanine.mp4", produce)
        assert seen[0] != seen[1]
        assert all(p.name.startswith(".mezzanine.") and p.suffix == ".mp4" for p in seen)
        assert [p.name for p in tmp_path.iterdir()] == ["mezzanine.mp4"]

    def test_removes_leftovers_of_a_killed_run_but_not_fresh_ones(self, tmp_path: Path) -> None:
        # 強制終了されると一時ファイルが残る。中間素材は数百 MB あるので、次に作るときに片付ける
        old = tmp_path / ".mezzanine.0a1b2c3d.partial.mp4"
        fresh = tmp_path / ".mezzanine.4e5f6a7b.partial.mp4"  # 別の worker が書いている最中
        other = tmp_path / ".proxy.0a1b2c3d.partial.mp4"
        for path in (old, fresh, other):
            path.write_bytes(b"half")
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        os.utime(other, (two_days_ago, two_days_ago))
        write_atomically(tmp_path / "mezzanine.mp4", lambda partial: partial.write_bytes(b"data"))
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            fresh.name,
            other.name,
            "mezzanine.mp4",
        ]

    def test_leftover_that_cannot_be_removed_does_not_stop_the_work(self, tmp_path: Path) -> None:
        stuck = tmp_path / ".mezzanine.0a1b2c3d.partial.mp4"
        stuck.mkdir()  # ファイルとして消せない
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(stuck, (two_days_ago, two_days_ago))
        dest = tmp_path / "mezzanine.mp4"
        write_atomically(dest, lambda partial: partial.write_bytes(b"data"))
        assert dest.read_bytes() == b"data"

    def test_leaves_no_file_when_production_fails(self, tmp_path: Path) -> None:
        dest = tmp_path / "proxy.mp4"

        def produce(partial: Path) -> None:
            partial.write_bytes(b"half")
            raise ExternalToolError("boom")

        with pytest.raises(ExternalToolError):
            write_atomically(dest, produce)
        assert list(tmp_path.iterdir()) == []

    def test_fails_when_nothing_was_written(self, tmp_path: Path) -> None:
        with pytest.raises(ExternalToolError):
            write_atomically(tmp_path / "x.wav", lambda partial: None)


def test_tool_rejects_unreadable_ffprobe_output(tmp_path: Path) -> None:
    fake_ffprobe = tmp_path / "ffprobe"
    fake_ffprobe.write_text(f"#!{sys.executable}\nprint('not json')\n")
    fake_ffprobe.chmod(0o755)
    tool = FfmpegMediaTool(ffprobe=str(fake_ffprobe))
    with pytest.raises(UnsupportedMediaError):
        tool.probe(tmp_path / "rec.mov")
