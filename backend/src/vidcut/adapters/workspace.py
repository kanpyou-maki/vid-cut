"""ワークスペース（既定 ~/VidCut/）のファイル: 録画ファイルごとの生成物と、録画ファイルの同一性。"""

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from vidcut.domain.titles import strip_invisible

_SAFE_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*")
_SAMPLE_BYTES = 1024 * 1024
_EXPORTS_DIRECTORY = "exports"
_EXPORT_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,8}")
# パスの区切り・制御文字など、ファイル名に使えない（または紛らわしい）文字
_UNSAFE_TITLE_CHARS = re.compile(r"[/\\:\x00-\x1f\x7f]")
# 日本語は 1 文字 3 バイト。拡張子と一時ファイルの接頭辞を足しても 255 バイトに収まる長さ
_MAX_TITLE_CHARS = 60
_FALLBACK_TITLE = "untitled"


class FileArtifactStore:
    """ArtifactStore の実装。生成物は <root>/recordings/<recording_id>/<name> に置く。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, recording_id: str, name: str) -> Path:
        """書き込み先として渡すため、親のディレクトリを作っておく。"""
        file = self._file(recording_id, name)
        file.parent.mkdir(parents=True, exist_ok=True)
        return file

    def read_json(self, recording_id: str, name: str) -> object | None:
        path = self._file(recording_id, name)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            data: object = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON として読めません: {path}") from e
        return data

    def write_json(self, recording_id: str, name: str, data: object) -> None:
        path = self.path(recording_id, name)
        _write_atomically(path, lambda file: json.dump(data, file, ensure_ascii=False))

    def _file(self, recording_id: str, name: str) -> Path:
        return self._root / "recordings" / _safe(recording_id) / _safe(name)


class FileExportStore:
    """ExportStore の実装。書き出しは <root>/exports/<レクチャー名>/<レクチャー名><suffix> に置く。

    レクチャー名は録画ファイルの名前や人の入力から来るので、フォルダの外を指せない名前に直して使う。
    同じ名前のレクチャーが 2 つあると、同じ場所に書き出す（後のものが残る）。
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, title: str, suffix: str) -> Path:
        if not _EXPORT_SUFFIX.fullmatch(suffix):
            raise ValueError(f"使えない拡張子です: {suffix!r}")
        name = _export_name(title)
        exports = self._root / _EXPORTS_DIRECTORY
        directory = exports / name
        # シンボリックリンクをたどると、ワークスペースの外に書き出してしまう
        for candidate in (exports, directory):
            if candidate.is_symlink():
                raise ValueError(f"書き出し先がシンボリックリンクです: {candidate}")
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{name}{suffix}"

    def write_text(self, title: str, suffix: str, text: str) -> Path:
        path = self.path(title, suffix)
        _write_atomically(path, lambda file: file.write(text))
        return path


def file_fingerprint(path: Path) -> str:
    """サイズ + 更新日時 + 先頭と末尾 1MB のハッシュ（Design Doc 4 章）。全体は読まない。"""
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as file:
        digest.update(file.read(_SAMPLE_BYTES))
        if stat.st_size > _SAMPLE_BYTES:
            file.seek(max(stat.st_size - _SAMPLE_BYTES, _SAMPLE_BYTES))
            digest.update(file.read(_SAMPLE_BYTES))
    return f"{stat.st_size}-{stat.st_mtime_ns}-{digest.hexdigest()[:16]}"


def _write_atomically(path: Path, write: Callable[[TextIO], object]) -> None:
    """一時ファイルに書き終えてから置き換える（途中の状態を残さない）。"""
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            write(file)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _export_name(title: str) -> str:
    """レクチャー名をファイル名に使える形に直す。区切り文字は置き換え、先頭と末尾の「.」は落とす。

    見えない文字（双方向制御文字など）は除き、NFC にそろえる（見た目の違う同じ名前を作らない）。
    """
    cleaned = strip_invisible(_UNSAFE_TITLE_CHARS.sub("_", title)).strip().strip(" .")
    # 切り詰めた結果の末尾に「.」や空白が残らないよう、もう一度落とす
    return cleaned[:_MAX_TITLE_CHARS].strip(" .") or _FALLBACK_TITLE


def _safe(name: str) -> str:
    """ワークスペースの外を指す名前（.. や / を含むもの）を拒む。"""
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError(f"使えない名前です: {name!r}")
    return name
