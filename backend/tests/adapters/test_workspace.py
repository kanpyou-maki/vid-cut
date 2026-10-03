import os
from pathlib import Path

import pytest

from vidcut.adapters.workspace import FileArtifactStore, file_fingerprint


class TestFileArtifactStore:
    def test_path_is_inside_recording_directory(self, tmp_path: Path) -> None:
        store = FileArtifactStore(tmp_path)
        path = store.path("r1", "proxy.mp4")
        assert path == tmp_path / "recordings" / "r1" / "proxy.mp4"
        assert path.parent.is_dir()

    def test_json_round_trip_keeps_japanese(self, tmp_path: Path) -> None:
        store = FileArtifactStore(tmp_path)
        store.write_json("r1", "a.json", {"text": "こんにちは", "n": [1, 2]})
        assert store.read_json("r1", "a.json") == {"text": "こんにちは", "n": [1, 2]}
        assert "こんにちは" in (tmp_path / "recordings" / "r1" / "a.json").read_text()

    def test_missing_json_is_none(self, tmp_path: Path) -> None:
        assert FileArtifactStore(tmp_path).read_json("r1", "a.json") is None

    def test_broken_json_is_value_error(self, tmp_path: Path) -> None:
        store = FileArtifactStore(tmp_path)
        store.path("r1", "a.json").write_text("{broken")
        with pytest.raises(ValueError):
            store.read_json("r1", "a.json")

    def test_write_leaves_no_temporary_files(self, tmp_path: Path) -> None:
        store = FileArtifactStore(tmp_path)
        store.write_json("r1", "a.json", [1])
        store.write_json("r1", "a.json", [2])
        assert [p.name for p in (tmp_path / "recordings" / "r1").iterdir()] == ["a.json"]

    @pytest.mark.parametrize(
        ("recording_id", "name"),
        [("../x", "a.json"), ("r1", "../../etc"), ("", "a.json"), ("r1", ".hidden"), ("r/1", "a")],
    )
    def test_rejects_names_that_escape_the_workspace(
        self, tmp_path: Path, recording_id: str, name: str
    ) -> None:
        with pytest.raises(ValueError):
            FileArtifactStore(tmp_path).path(recording_id, name)


class TestFileFingerprint:
    def test_same_content_and_time_gives_same_value(self, tmp_path: Path) -> None:
        a = tmp_path / "a.mov"
        b = tmp_path / "b.mov"
        for path in (a, b):
            path.write_bytes(b"x" * 3_000_000)
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        assert file_fingerprint(a) == file_fingerprint(b)

    def test_change_in_the_tail_is_detected(self, tmp_path: Path) -> None:
        path = tmp_path / "a.mov"
        path.write_bytes(b"x" * 3_000_000)
        os.utime(path, ns=(1, 1))
        before = file_fingerprint(path)
        path.write_bytes(b"x" * 2_999_999 + b"y")
        os.utime(path, ns=(1, 1))
        assert file_fingerprint(path) != before

    def test_small_file(self, tmp_path: Path) -> None:
        path = tmp_path / "a.mov"
        path.write_bytes(b"abc")
        assert file_fingerprint(path).startswith("3-")
