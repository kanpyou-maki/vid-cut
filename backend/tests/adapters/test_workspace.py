import os
from pathlib import Path

import pytest

from vidcut.adapters.workspace import FileArtifactStore, FileExportStore, file_fingerprint


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

    def test_reading_creates_no_directory(self, tmp_path: Path) -> None:
        FileArtifactStore(tmp_path).read_json("never", "a.json")
        assert not (tmp_path / "recordings" / "never").exists()

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

    def test_failed_write_keeps_the_previous_file_and_no_temporary_files(
        self, tmp_path: Path
    ) -> None:
        store = FileArtifactStore(tmp_path)
        store.write_json("r1", "a.json", [1])
        with pytest.raises(TypeError):
            store.write_json("r1", "a.json", {"not json": object()})
        assert store.read_json("r1", "a.json") == [1]
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


class TestFileExportStore:
    def test_path_is_named_after_the_lecture(self, tmp_path: Path) -> None:
        path = FileExportStore(tmp_path).path("S05-12 環境構築", ".xml")
        assert path == tmp_path / "exports" / "S05-12 環境構築" / "S05-12 環境構築.xml"
        assert path.parent.is_dir()

    def test_write_text_replaces_the_previous_export(self, tmp_path: Path) -> None:
        store = FileExportStore(tmp_path)
        store.write_text("L", ".xml", "<old/>")
        path = store.write_text("L", ".xml", "<新しい/>")
        assert path == store.path("L", ".xml")
        assert path.read_text(encoding="utf-8") == "<新しい/>"
        assert [p.name for p in path.parent.iterdir()] == ["L.xml"]

    @pytest.mark.parametrize(
        ("title", "name"),
        [
            ("../../etc/passwd", "_.._etc_passwd"),
            ("a/b\\c:d", "a_b_c_d"),
            ("..", "untitled"),
            ("  . ", "untitled"),
            ("", "untitled"),
            ("line\nbreak\x00", "line_break_"),
            (".hidden", "hidden"),
            ("-rf", "-rf"),
        ],
    )
    def test_titles_cannot_escape_the_exports_directory(
        self, tmp_path: Path, title: str, name: str
    ) -> None:
        path = FileExportStore(tmp_path).path(title, ".mp4")
        assert path == tmp_path / "exports" / name / f"{name}.mp4"

    @pytest.mark.parametrize(
        ("title", "name"),
        [
            ("report\u202egpj.exe", "reportgpj.exe"),  # 右から左への上書きで見た目を偽れない
            ("a\u200bb\u2028c\u2029d", "abcd"),
            ("カ\u3099イト\u3099", "ガイド"),  # NFD のファイル名から来た題名
            ("\x85\u200b", "untitled"),
        ],
    )
    def test_invisible_characters_are_removed_and_names_are_composed(
        self, tmp_path: Path, title: str, name: str
    ) -> None:
        path = FileExportStore(tmp_path).path(title, ".xml")
        assert path == tmp_path / "exports" / name / f"{name}.xml"

    def test_refuses_a_lecture_directory_that_is_a_symlink(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        exports = tmp_path / "ws" / "exports"
        exports.mkdir(parents=True)
        (exports / "L").symlink_to(outside, target_is_directory=True)
        store = FileExportStore(tmp_path / "ws")
        with pytest.raises(ValueError, match="シンボリックリンク"):
            store.write_text("L", ".xml", "<x/>")
        assert list(outside.iterdir()) == []

    def test_refuses_an_exports_directory_that_is_a_symlink(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / "exports").symlink_to(outside, target_is_directory=True)
        with pytest.raises(ValueError, match="シンボリックリンク"):
            FileExportStore(workspace).path("L", ".mp4")
        assert list(outside.iterdir()) == []

    def test_long_titles_are_shortened_to_fit_a_file_name(self, tmp_path: Path) -> None:
        path = FileExportStore(tmp_path).path("あ" * 300, ".mp4")
        assert len(path.name.encode()) <= 200
        assert path.parent.is_dir()

    def test_shortened_title_does_not_end_with_a_dot_or_space(self, tmp_path: Path) -> None:
        path = FileExportStore(tmp_path).path("あ" * 59 + ". 続き", ".mp4")
        assert path.parent.name == "あ" * 59

    @pytest.mark.parametrize("suffix", ["", "xml", ".x/y", "../.xml", ".mp4 "])
    def test_rejects_suffixes_that_are_not_a_plain_extension(
        self, tmp_path: Path, suffix: str
    ) -> None:
        with pytest.raises(ValueError):
            FileExportStore(tmp_path).path("L", suffix)


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
