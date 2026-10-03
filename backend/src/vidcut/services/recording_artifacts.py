"""録画ファイルの生成物のうち、画面が読むもの（プレビュー用の動画と波形のピーク値）。"""

from pathlib import Path

from vidcut.pipeline import serialization as ser
from vidcut.pipeline.analysis import PEAKS_FILE, PROXY_FILE
from vidcut.pipeline.ports import ArtifactStore, NotFoundError, Peaks, RecordingRepository


class RecordingArtifacts:
    def __init__(self, *, recordings: RecordingRepository, store: ArtifactStore) -> None:
        self._recordings = recordings
        self._store = store

    def proxy_path(self, recording_id: str) -> Path:
        """プレビュー用の動画の場所。解析の proxy の段が終わるまでは NotFoundError。"""
        self._require_registered(recording_id)
        proxy = self._store.path(recording_id, PROXY_FILE)
        if not proxy.is_file():
            raise NotFoundError(f"プレビュー用の動画がまだありません: {recording_id}")
        return proxy

    def peaks(self, recording_id: str) -> Peaks:
        """波形のピーク値。まだなければ NotFoundError、形が壊れていれば ValueError。"""
        self._require_registered(recording_id)
        data = self._store.read_json(recording_id, PEAKS_FILE)
        if data is None:
            raise NotFoundError(f"波形のピーク値がまだありません: {recording_id}")
        return ser.decode(data, ser.peaks_from)

    def _require_registered(self, recording_id: str) -> None:
        """未登録の id では、生成物のフォルダも作らない（ArtifactStore.path は親を作る）。"""
        if self._recordings.get(recording_id) is None:
            raise NotFoundError(f"録画ファイルが登録されていません: {recording_id}")
