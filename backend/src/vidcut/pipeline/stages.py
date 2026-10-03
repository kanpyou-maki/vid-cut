"""段ごとの生成物のキャッシュ（Design Doc 3-2）。

各段のキーは「前の段のキー + 段の名前 + 段の設定」のハッシュ。起点は録画ファイルの fingerprint。
キーを stages.json に記録し、キーが一致して生成物が残っていれば、その段を飛ばす。
"""

import hashlib
import json
from pathlib import Path

from vidcut.domain.models import Recording
from vidcut.pipeline.ports import ArtifactStore

_MANIFEST = "stages.json"


def stage_key(previous: str, name: str, settings: object) -> str:
    payload = json.dumps([previous, name, settings], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def require_source(recording: Recording) -> Path:
    source = Path(recording.source_path)
    if not source.is_file():
        raise FileNotFoundError(f"元の録画ファイルが見つかりません: {recording.source_path}")
    return source


class StageCache:
    def __init__(self, store: ArtifactStore, recording_id: str) -> None:
        self._store = store
        self._recording_id = recording_id

    def is_current(self, name: str, key: str, artifact: str) -> bool:
        manifest = self._manifest()
        exists = self._store.path(self._recording_id, artifact).exists()
        return manifest.get(name) == key and exists

    def mark(self, name: str, key: str) -> None:
        """生成物を書き終えてから呼ぶ。"""
        self._store.write_json(self._recording_id, _MANIFEST, {**self._manifest(), name: key})

    def _manifest(self) -> dict[str, str]:
        try:
            data = self._store.read_json(self._recording_id, _MANIFEST)
        except ValueError:
            return {}  # 壊れていれば、すべての段を作り直す
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}
