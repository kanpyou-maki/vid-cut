"""書き出し用の中間素材（ジョブ make_mezzanine。ADR-002）。"""

from pathlib import Path

from vidcut.domain.models import Recording
from vidcut.pipeline.ports import ArtifactStore, MediaTool, ProgressReporter
from vidcut.pipeline.stages import StageCache, require_source, stage_key

MEZZANINE_FILE = "mezzanine.mp4"
# ffmpeg の引数（フレームレート・画質）を変えたら上げる
_FORMAT_VERSION = 1


def mezzanine_path(store: ArtifactStore, recording_id: str) -> Path:
    return store.path(recording_id, MEZZANINE_FILE)


def make_mezzanine(
    recording: Recording, media: MediaTool, store: ArtifactStore, report: ProgressReporter
) -> Path:
    """中間素材を作って場所を返す。同じ録画ファイルから作ったものがあれば作り直さない。

    作り直さないときは元の録画ファイルを必要としない（書き出しは中間素材だけあればできる）。
    """
    cache = StageCache(store, recording.id)
    key = stage_key(recording.fingerprint, "mezzanine", _FORMAT_VERSION)
    path = mezzanine_path(store, recording.id)
    if not cache.is_current("mezzanine", key, MEZZANINE_FILE):
        source = require_source(recording)
        report("mezzanine", 0.0)
        media.make_mezzanine(
            source,
            path,
            duration_ms=recording.duration_ms,
            on_progress=lambda fraction: report("mezzanine", fraction),
        )
        cache.mark("mezzanine", key)
    return path
