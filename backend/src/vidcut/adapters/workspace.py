"""ワークスペース（既定 ~/VidCut/）のファイル: 録画ファイルごとの生成物と、録画ファイルの同一性。"""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

_SAFE_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*")
_SAMPLE_BYTES = 1024 * 1024


class FileArtifactStore:
    """ArtifactStore の実装。生成物は <root>/recordings/<recording_id>/<name> に置く。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, recording_id: str, name: str) -> Path:
        directory = self._root / "recordings" / _safe(recording_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / _safe(name)

    def read_json(self, recording_id: str, name: str) -> object | None:
        path = self.path(recording_id, name)
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
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False)
            os.replace(temp, path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise


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


def _safe(name: str) -> str:
    """ワークスペースの外を指す名前（.. や / を含むもの）を拒む。"""
    if not _SAFE_NAME.fullmatch(name):
        raise ValueError(f"使えない名前です: {name!r}")
    return name
