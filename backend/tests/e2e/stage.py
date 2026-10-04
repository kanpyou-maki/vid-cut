"""E2E の舞台: 専用のフォルダ（ワークスペースと素材）と、偽の ML・偽の判定で組み立てた App。"""

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tests.e2e.material import make_lesson as make_real_lesson
from tests.e2e.script import ScriptedJudge, ScriptedTranscriber, SilentVad
from tests.pipeline.fakes import FakeAligner
from vidcut.bootstrap import App, MlTools, build_app

MARKER = "vidcut-e2e-root"
"""このスクリプトが作ったフォルダの目印。これがないフォルダは、空でないかぎり消さない。"""
LESSON_FOLDER = "講座 素材"  # 日本語と空白を含むパスを通す
LESSON_NAMES = ("lesson-1.mov", "lesson-2.mov")
_TONES_HZ = (440, 660)

LessonMaker = Callable[[Path, int], None]


@dataclass(frozen=True)
class Stage:
    root: Path
    workspace: Path
    home: Path  # /api/fs と /api/imports が見せる範囲
    lessons: tuple[Path, ...]


def prepare(root: Path, *, make_lesson: LessonMaker = make_real_lesson) -> Stage:
    """root をまっさらにして、ワークスペースと素材を作る。

    消すのは、前回このスクリプトが作ったフォルダ（目印がある）だけ。
    実データのフォルダを誤って指定しても、消さずに失敗する。
    """
    root = root.resolve()
    if root.exists():
        if any(root.iterdir()) and not (root / MARKER).is_file():
            raise ValueError(f"E2E 用のフォルダではありません（{MARKER} がない）: {root}")
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / MARKER).write_text("vid-cut の E2E が作ったフォルダ。実行のたびに消して作り直す\n")
    workspace, home = root / "workspace", root / "home"
    workspace.mkdir()
    folder = home / LESSON_FOLDER
    folder.mkdir(parents=True)
    lessons = tuple(folder / name for name in LESSON_NAMES)
    for lesson, tone_hz in zip(lessons, _TONES_HZ, strict=True):
        make_lesson(lesson, tone_hz)
    return Stage(root=root, workspace=workspace, home=home, lessons=lessons)


def fake_app(workspace: Path) -> App:
    """ML と判定だけを偽の実装に差し替える。ffmpeg と SQLite は実物。"""
    ml = MlTools(vad=SilentVad(), transcriber=ScriptedTranscriber(), aligner=FakeAligner())
    return build_app(workspace, ml=ml, model=ScriptedJudge())
