import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.e2e.script import DURATION_MS, LESSON_NAMES, LINES, RETAKE_REASON
from tests.e2e.stage import MARKER, fake_app, prepare
from vidcut.domain.models import CutKind, JobKind
from vidcut.services.lecture_views import LectureStatus

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg が必要")
BOUNDARY_TOLERANCE_MS = 100  # 無音の検出（実物の ffmpeg）の端は、音の切り替わりから少しずれる


class TestPrepare:
    def test_refuses_a_folder_that_it_did_not_make(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "大事なファイル.txt").write_text("消さない")

        with pytest.raises(ValueError, match="E2E 用のフォルダではありません"):
            prepare(root, make_lesson=_empty_lesson)

        assert (root / "大事なファイル.txt").read_text() == "消さない"

    def test_refuses_a_file(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.write_text("消さない")

        with pytest.raises(ValueError, match="E2E 用のフォルダではありません"):
            prepare(root, make_lesson=_empty_lesson)

        assert root.read_text() == "消さない"

    def test_makes_the_workspace_and_the_lessons(self, tmp_path: Path) -> None:
        stage = prepare(tmp_path / "root", make_lesson=_empty_lesson)

        assert (stage.root / MARKER).is_file()
        assert stage.workspace.is_dir()
        assert [lesson.name for lesson in stage.lessons] == list(LESSON_NAMES)
        assert all(
            lesson.is_file() and lesson.parent.parent == stage.home for lesson in stage.lessons
        )

    def test_accepts_an_empty_folder(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()

        assert prepare(root, make_lesson=_empty_lesson).root == root

    def test_starts_over_from_a_clean_state(self, tmp_path: Path) -> None:
        first = prepare(tmp_path / "root", make_lesson=_empty_lesson)
        (first.workspace / "前回の残り").write_text("x")

        second = prepare(tmp_path / "root", make_lesson=_empty_lesson)

        assert not (second.workspace / "前回の残り").exists()

    def test_gives_each_lesson_a_different_tone(self, tmp_path: Path) -> None:
        # 中身が同じだと、2 本目は「登録済み」になって取り込まれない
        tones: list[int] = []

        prepare(tmp_path / "root", make_lesson=lambda dest, tone: tones.append(tone))

        assert len(set(tones)) == len(LESSON_NAMES)


def _empty_lesson(dest: Path, tone_hz: int) -> None:
    dest.write_bytes(b"")


@needs_ffmpeg
@pytest.mark.integration
class TestFlow:
    """実物の ffmpeg と、偽の ML・偽の判定で、取り込みから書き出しまでが決まった結果になる。"""

    def test_analysis_follows_the_script(self, tmp_path: Path) -> None:
        stage = prepare(tmp_path / "root")
        app = fake_app(stage.workspace)
        try:
            result = app.imports.import_paths([stage.lessons[0]])
            assert app.worker().run_until_idle() > 0

            (summary,) = app.lecture_views.summaries()
            detail = app.lecture_views.detail(summary.lecture.id)
            (recording,) = result.added
            analysis = detail.analyses[recording.id]
        finally:
            app.close()

        assert summary.status is LectureStatus.READY
        assert abs(recording.duration_ms - DURATION_MS) <= BOUNDARY_TOLERANCE_MS
        assert len(analysis.chunks) == len(LINES)
        for chunk, line in zip(analysis.chunks, LINES, strict=True):
            assert abs(chunk.span.start_ms - line.span.start_ms) <= BOUNDARY_TOLERANCE_MS
            assert abs(chunk.span.end_ms - line.span.end_ms) <= BOUNDARY_TOLERANCE_MS
        assert "".join(token.text for token in analysis.tokens) == "".join(
            line.text for line in LINES
        )
        assert [s.reason for s in analysis.suggestions if s.kind is CutKind.FILLER] == [
            "フィラー「えーと」"
        ]
        assert len(analysis.review_marks) == 1
        assert detail.judgement is not None
        assert [(s.kind, s.reason) for s in detail.judgement.suggestions] == [
            (CutKind.RETAKE, RETAKE_REASON)
        ]

    def test_export_writes_the_kept_ranges(self, tmp_path: Path) -> None:
        stage = prepare(tmp_path / "root")
        app = fake_app(stage.workspace)
        try:
            app.imports.import_paths([stage.lessons[0]])
            app.worker().run_until_idle()
            (summary,) = app.lecture_views.summaries()
            app.exports.request(summary.lecture.id, JobKind.EXPORT_PREMIERE)
            app.worker().run_until_idle()
        finally:
            app.close()

        (xml,) = (stage.workspace / "exports").rglob("*.xml")
        video = ET.parse(xml).getroot().find("./sequence/media/video/track")
        assert video is not None
        # 残るのは 3 つ: こんにちは。／今日は編集の話をします。／（えーと、を除いた）最後です。
        assert len(video.findall("clipitem")) == 3
