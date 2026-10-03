"""録画ファイルの取り込み（US-10）。登録して、解析と中間素材のジョブを積む。"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from vidcut.domain.models import Job, JobKind, Lecture, Recording
from vidcut.pipeline.ports import (
    ExternalToolError,
    Fingerprinter,
    JobQueue,
    LectureRepository,
    MediaTool,
    RecordingRepository,
)

VIDEO_SUFFIXES = frozenset({".mov", ".mp4", ".m4v"})


@dataclass(frozen=True)
class ImportResult:
    added: tuple[Recording, ...]
    existing: tuple[Recording, ...]  # 同じファイルが登録済み（解析は積み直さない）
    failed: tuple[tuple[str, str], ...]  # (パス, 理由)


class ImportService:
    def __init__(
        self,
        *,
        recordings: RecordingRepository,
        lectures: LectureRepository,
        queue: JobQueue,
        media: MediaTool,
        fingerprint: Fingerprinter,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._recordings = recordings
        self._lectures = lectures
        self._queue = queue
        self._media = media
        self._fingerprint = fingerprint
        self._new_id = new_id

    def import_paths(self, paths: Sequence[Path]) -> ImportResult:
        """ファイルまたはフォルダ（直下の動画ファイル）を取り込む。1 本の失敗で全体を止めない。"""
        added: list[Recording] = []
        existing: list[Recording] = []
        failed: list[tuple[str, str]] = []
        for path in _expand(paths):
            try:
                recording, is_new = self._import_one(path)
            except (OSError, ValueError, ExternalToolError) as e:
                failed.append((str(path), _message(e)))
                continue
            (added if is_new else existing).append(recording)
        return ImportResult(tuple(added), tuple(existing), tuple(failed))

    def _import_one(self, path: Path) -> tuple[Recording, bool]:
        source = path.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"録画ファイルが見つかりません: {path}")
        fingerprint = self._fingerprint(source)
        found = self._recordings.find_by_fingerprint(fingerprint)
        if found is not None:
            return found, False
        probe = self._media.probe(source)
        recording = Recording(
            id=self._new_id(),
            source_path=str(source),
            fingerprint=fingerprint,
            duration_ms=probe.duration_ms,
            recorded_at=probe.recorded_at,
            media=probe.media,
        )
        self._recordings.add(recording)
        self._lectures.save(
            Lecture(id=self._new_id(), title=source.stem, recording_ids=(recording.id,))
        )
        for kind in (JobKind.ANALYZE_RECORDING, JobKind.MAKE_MEZZANINE):
            self._queue.enqueue(Job(id=self._new_id(), kind=kind, target_id=recording.id))
        return recording, True


def _expand(paths: Sequence[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            videos = (
                p for p in path.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
            )
            expanded.extend(sorted(videos, key=lambda p: p.name.lower()))
        else:
            expanded.append(path)
    return expanded


def _message(error: Exception) -> str:
    return str(error) or type(error).__name__
