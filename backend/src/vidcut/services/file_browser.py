"""投入するファイルとフォルダを選ぶための簡易ブラウザ（Design Doc 3-5・3-5-1、ADR-004）。

ホームディレクトリ配下の、隠しでないフォルダと動画ファイルだけを見せる。
パスは実体を解決してから判定する（`..` とシンボリックリンクで外へ出られないようにする）。
"""

from dataclasses import dataclass
from pathlib import Path

from vidcut.pipeline.ports import InvalidInputError, NotFoundError
from vidcut.services.imports import VIDEO_SUFFIXES

MAX_ENTRIES = 1000
"""1 つのフォルダで返す件数の上限（巨大なフォルダで応答が膨らまないようにする）。"""

_OUTSIDE = "ホームフォルダの外は選べません"
_HIDDEN = "隠しファイル・隠しフォルダは選べません"


@dataclass(frozen=True)
class Entry:
    name: str
    path: Path  # 実体を解決した絶対パス
    is_directory: bool


@dataclass(frozen=True)
class Listing:
    path: Path
    parent: Path | None  # ホームでは None（それより上へは行けない）
    entries: tuple[Entry, ...]  # フォルダが先、その中は名前順
    truncated: bool  # MAX_ENTRIES を超えたので、残りを省いた


class FileBrowser:
    def __init__(self, home: Path) -> None:
        self._home = home.resolve()

    def list(self, path: Path | None = None) -> Listing:
        """フォルダの中の、選べるフォルダと動画ファイル。path を省くとホーム。"""
        directory = self._home if path is None else self._resolve(path)
        if not directory.is_dir():
            raise InvalidInputError("フォルダではありません")
        try:
            children = sorted(directory.iterdir(), key=lambda child: child.name.lower())
        except PermissionError as e:
            raise InvalidInputError("このフォルダを読む権限がありません") from e
        entries = [entry for child in children if (entry := self._entry(child)) is not None]
        entries.sort(key=lambda entry: not entry.is_directory)  # 安定な並べ替え: 名前順は保つ
        return Listing(
            path=directory,
            parent=None if directory == self._home else directory.parent,
            entries=tuple(entries[:MAX_ENTRIES]),
            truncated=len(entries) > MAX_ENTRIES,
        )

    def import_targets(self, path: Path) -> tuple[Path, ...]:
        """取り込む動画ファイル。フォルダなら、その直下の選べる動画ファイル（名前順）。"""
        resolved = self._resolve(path)
        if not resolved.is_dir():
            return (resolved,)
        listing = self.list(resolved)
        return tuple(entry.path for entry in listing.entries if not entry.is_directory)

    def _resolve(self, path: Path) -> Path:
        """実体を解決し、ホーム配下の隠しでない場所であることを確かめる。"""
        if not path.is_absolute():
            raise InvalidInputError("絶対パスで指定してください")
        # ホームの外は、あるかないかも答えない（存在を確かめる前に弾く）
        self._require_visible(path.resolve())
        try:
            resolved = path.resolve(strict=True)
        except (FileNotFoundError, NotADirectoryError) as e:
            raise NotFoundError("ファイルまたはフォルダが見つかりません") from e
        # 存在したものについては、シンボリックリンクをたどった先でもう一度確かめる
        self._require_visible(resolved)
        return resolved

    def _require_visible(self, resolved: Path) -> None:
        if not resolved.is_relative_to(self._home):
            raise InvalidInputError(_OUTSIDE)
        if any(part.startswith(".") for part in resolved.relative_to(self._home).parts):
            raise InvalidInputError(_HIDDEN)

    def _entry(self, child: Path) -> Entry | None:
        """一覧に出すものだけを返す。隠しファイル、外を指すリンク、動画以外のファイルは出さない。"""
        if child.name.startswith("."):
            return None
        try:
            resolved = child.resolve(strict=True)
            self._require_visible(resolved)
            is_directory = resolved.is_dir()
        except (OSError, InvalidInputError):
            # 切れたリンクや、外・隠しフォルダを指すリンクは、選べないので見せない
            return None
        if not is_directory and child.suffix.lower() not in VIDEO_SUFFIXES:
            return None
        return Entry(name=child.name, path=resolved, is_directory=is_directory)
