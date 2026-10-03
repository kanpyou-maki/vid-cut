import os
from pathlib import Path

import pytest

from vidcut.pipeline.ports import InvalidInputError, NotFoundError
from vidcut.services.file_browser import MAX_ENTRIES, FileBrowser


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """home/Movies に動画 2 本とフォルダ、home/.ssh に鍵、home の外に outside/secret.mov。"""
    home = tmp_path / "home"
    movies = home / "Movies"
    (movies / "course").mkdir(parents=True)
    for name in ("b.MOV", "a.mp4", "notes.txt", ".hidden.mov"):
        (movies / name).write_bytes(b"x")
    (movies / "course" / "c.m4v").write_bytes(b"x")
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_ed25519").write_bytes(b"key")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.mov").write_bytes(b"x")
    return home


@pytest.fixture
def browser(home: Path) -> FileBrowser:
    return FileBrowser(home)


class TestList:
    def test_home_is_listed_by_default_and_has_no_parent(
        self, browser: FileBrowser, home: Path
    ) -> None:
        listing = browser.list()
        assert (listing.path, listing.parent) == (home.resolve(), None)
        assert [(e.name, e.is_directory) for e in listing.entries] == [("Movies", True)]

    def test_shows_folders_first_then_videos_by_name(
        self, browser: FileBrowser, home: Path
    ) -> None:
        listing = browser.list(home / "Movies")
        assert listing.parent == home.resolve()
        assert [(e.name, e.is_directory) for e in listing.entries] == [
            ("course", True),
            ("a.mp4", False),
            ("b.MOV", False),
        ]
        assert listing.entries[1].path == (home / "Movies" / "a.mp4").resolve()
        assert not listing.truncated

    @pytest.mark.parametrize("relative", ["../outside", "Movies/../../outside", ".."])
    def test_paths_outside_home_are_refused(
        self, browser: FileBrowser, home: Path, relative: str
    ) -> None:
        with pytest.raises(InvalidInputError, match="ホーム"):
            browser.list(home / relative)

    def test_absolute_paths_outside_home_are_refused_even_if_missing(
        self, browser: FileBrowser
    ) -> None:
        # ホームの外は、あるかないかも答えない
        with pytest.raises(InvalidInputError, match="ホーム"):
            browser.list(Path("/no/such/folder"))
        with pytest.raises(InvalidInputError, match="ホーム"):
            browser.list(Path("/etc"))

    @pytest.mark.parametrize("relative", [".ssh", "Movies/.git", ".ssh/../.ssh"])
    def test_hidden_folders_are_refused(
        self, browser: FileBrowser, home: Path, relative: str
    ) -> None:
        (home / "Movies" / ".git").mkdir()
        with pytest.raises(InvalidInputError, match="隠し"):
            browser.list(home / relative)

    def test_symlink_that_leaves_home_is_refused_and_not_listed(
        self, browser: FileBrowser, home: Path, tmp_path: Path
    ) -> None:
        (home / "Movies" / "link").symlink_to(tmp_path / "outside", target_is_directory=True)
        (home / "Movies" / "keys").symlink_to(home / ".ssh", target_is_directory=True)
        (home / "Movies" / "linked.mov").symlink_to(tmp_path / "outside" / "secret.mov")
        names = [e.name for e in browser.list(home / "Movies").entries]
        assert names == ["course", "a.mp4", "b.MOV"]
        with pytest.raises(InvalidInputError, match="ホーム"):
            browser.list(home / "Movies" / "link")
        with pytest.raises(InvalidInputError, match="隠し"):
            browser.list(home / "Movies" / "keys")

    def test_link_is_judged_by_what_it_points_to_not_by_its_name(
        self, browser: FileBrowser, home: Path
    ) -> None:
        # 動画の名前を付けたリンクで、動画以外のファイルを取り込ませない
        (home / "Movies" / "disguised.mov").symlink_to(home / "Movies" / "notes.txt")
        (home / "Movies" / "shortcut").symlink_to(home / "Movies" / "a.mp4")
        names = [e.name for e in browser.list(home / "Movies").entries]
        assert names == ["course", "a.mp4", "b.MOV", "shortcut"]
        targets = [t.name for t in browser.import_targets(home / "Movies")]
        assert targets == ["a.mp4", "b.MOV", "a.mp4"]

    def test_symlink_inside_home_is_followed(self, browser: FileBrowser, home: Path) -> None:
        (home / "shortcut").symlink_to(home / "Movies" / "course", target_is_directory=True)
        listing = browser.list(home / "shortcut")
        assert listing.path == (home / "Movies" / "course").resolve()
        assert [e.name for e in listing.entries] == ["c.m4v"]

    @pytest.mark.parametrize("name", ["a\x00b", "a" * 300])
    def test_names_the_file_system_cannot_handle_are_refused(
        self, browser: FileBrowser, home: Path, name: str
    ) -> None:
        # NUL 文字や長すぎる名前で、想定していない例外（500）にしない
        with pytest.raises(InvalidInputError, match="パスが正しくありません"):
            browser.list(home / "Movies" / name)
        with pytest.raises(InvalidInputError, match="パスが正しくありません"):
            browser.import_targets(home / "Movies" / name / "a.mov")

    def test_symlink_loop_is_refused(self, browser: FileBrowser, home: Path) -> None:
        (home / "loop-a").symlink_to(home / "loop-b")
        (home / "loop-b").symlink_to(home / "loop-a")
        with pytest.raises(InvalidInputError, match="パスが正しくありません"):
            browser.list(home / "loop-a")
        assert [e.name for e in browser.list().entries] == ["Movies"]

    def test_missing_folder(self, browser: FileBrowser, home: Path) -> None:
        with pytest.raises(NotFoundError):
            browser.list(home / "Movies" / "nope")

    def test_file_is_not_a_folder(self, browser: FileBrowser, home: Path) -> None:
        with pytest.raises(InvalidInputError, match="フォルダではありません"):
            browser.list(home / "Movies" / "a.mp4")

    @pytest.mark.skipif(os.geteuid() == 0, reason="root は権限に関係なく読める")
    def test_folder_that_cannot_be_read(self, browser: FileBrowser, home: Path) -> None:
        locked = home / "Locked"
        locked.mkdir()
        locked.chmod(0o000)
        try:
            with pytest.raises(InvalidInputError, match="権限"):
                browser.list(locked)
        finally:
            locked.chmod(0o755)

    def test_huge_folders_are_cut_off(self, browser: FileBrowser, home: Path) -> None:
        big = home / "big"
        big.mkdir()
        for index in range(MAX_ENTRIES + 5):
            (big / f"{index:05d}.mov").write_bytes(b"")
        listing = browser.list(big)
        assert len(listing.entries) == MAX_ENTRIES
        assert listing.truncated
        assert listing.entries[0].name == "00000.mov"


class TestImportTargets:
    def test_file_is_resolved(self, browser: FileBrowser, home: Path) -> None:
        targets = browser.import_targets(home / "Movies" / "course" / ".." / "a.mp4")
        assert targets == ((home / "Movies" / "a.mp4").resolve(),)

    def test_folder_expands_to_its_visible_videos(self, browser: FileBrowser, home: Path) -> None:
        (home / "Movies" / "linked.mov").symlink_to(home / ".ssh" / "id_ed25519")
        targets = browser.import_targets(home / "Movies")
        assert [t.name for t in targets] == ["a.mp4", "b.MOV"]

    @pytest.mark.parametrize("relative", ["../outside/secret.mov", ".ssh/id_ed25519", ".ssh"])
    def test_outside_and_hidden_paths_are_refused(
        self, browser: FileBrowser, home: Path, relative: str
    ) -> None:
        with pytest.raises(InvalidInputError):
            browser.import_targets(home / relative)

    def test_missing_file(self, browser: FileBrowser, home: Path) -> None:
        with pytest.raises(NotFoundError):
            browser.import_targets(home / "Movies" / "nope.mov")

    def test_path_below_a_file_is_missing(self, browser: FileBrowser, home: Path) -> None:
        with pytest.raises(NotFoundError):
            browser.import_targets(home / "Movies" / "a.mp4" / "b.mov")

    def test_file_that_is_not_a_video_is_refused(self, browser: FileBrowser, home: Path) -> None:
        # 一覧に出ないファイルは、直接指定しても取り込めない
        with pytest.raises(InvalidInputError, match="動画ファイル"):
            browser.import_targets(home / "Movies" / "notes.txt")

    def test_folder_with_many_subfolders_still_gives_all_its_videos(
        self, browser: FileBrowser, home: Path
    ) -> None:
        # 一覧は MAX_ENTRIES で打ち切るが、取り込みでは動画を落とさない
        big = home / "big"
        for index in range(MAX_ENTRIES + 2):
            (big / f"sub{index:05d}").mkdir(parents=True)
        (big / "a.mov").write_bytes(b"x")
        assert browser.list(big).truncated
        assert [t.name for t in browser.import_targets(big)] == ["a.mov"]

    def test_relative_path_is_refused(self, browser: FileBrowser) -> None:
        # サーバーの作業ディレクトリによって意味が変わる指定は受け付けない
        with pytest.raises(InvalidInputError, match="絶対パス"):
            browser.import_targets(Path("Movies/a.mp4"))
