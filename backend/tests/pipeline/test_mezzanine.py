from pathlib import Path

import pytest

from tests.pipeline.fakes import DirectoryStore, FakeMediaTool, make_recording
from vidcut.pipeline.mezzanine import make_mezzanine, mezzanine_path


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "lecture.mov"
    path.write_bytes(b"mov")
    return path


def test_creates_mezzanine_and_reports_progress(source: Path, tmp_path: Path) -> None:
    media, store = FakeMediaTool(), DirectoryStore(tmp_path / "ws")
    reported: list[tuple[str | None, float]] = []
    recording = make_recording(source)
    path = make_mezzanine(recording, media, store, lambda s, p: reported.append((s, p)))
    assert path == mezzanine_path(store, recording.id)
    assert path.read_bytes() == b"mezzanine"
    assert ("mezzanine", 0.5) in reported


def test_existing_mezzanine_is_reused(source: Path, tmp_path: Path) -> None:
    media, store = FakeMediaTool(), DirectoryStore(tmp_path / "ws")
    recording = make_recording(source)
    make_mezzanine(recording, media, store, lambda s, p: None)
    make_mezzanine(recording, media, store, lambda s, p: None)
    assert media.calls["make_mezzanine"] == 1


def test_missing_source_is_reported(source: Path, tmp_path: Path) -> None:
    recording = make_recording(source)
    source.unlink()
    with pytest.raises(FileNotFoundError):
        make_mezzanine(recording, FakeMediaTool(), DirectoryStore(tmp_path), lambda s, p: None)
