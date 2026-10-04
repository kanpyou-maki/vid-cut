"""書き出しの状態と保存先、Finder で開く（Design Doc 3-5 の「書き出しの状態と保存先」）。

書き出しの本体（services/export.py）と違い、ここは読むだけで、フォルダもファイルも作らない。
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from vidcut.domain.models import JobKind, Lecture
from vidcut.pipeline.ports import (
    ExportedFile,
    ExportStore,
    FileRevealer,
    InvalidInputError,
    JobQueue,
    LectureRepository,
    NotFoundError,
)
from vidcut.services.export import EXPORT_KINDS, MP4_SUFFIX, PREMIERE_SUFFIX
from vidcut.services.lecture_views import JobView

_SUFFIXES = (PREMIERE_SUFFIX, MP4_SUFFIX)
# この 2 つの文は、そのまま画面に出る（パスを入れない）
_NOTHING_EXPORTED = "書き出したファイルがまだありません"
_DESTINATION_REFUSED = "書き出し先がシンボリックリンクか、ワークスペースの外にあるため、開けません"


class RevealTarget(StrEnum):
    """Finder で選んで見せたもの。"""

    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True)
class ExportFileStatus:
    """1 つの形式の、書き出し先のファイルと、最新の書き出しジョブ（なければ None）。"""

    file: ExportedFile
    job: JobView | None


@dataclass(frozen=True)
class ExportStatus:
    """shared_with_other_lectures は、同じ場所に書き出すレクチャーがほかにあること。

    そのときは、書き出すと上書きになり、日時もほかのレクチャーのものでありうる。
    """

    directory: Path
    shared_with_other_lectures: bool
    premiere: ExportFileStatus
    mp4: ExportFileStatus


class ExportDestinations:
    def __init__(
        self,
        *,
        lectures: LectureRepository,
        queue: JobQueue,
        exports: ExportStore,
        revealer: FileRevealer,
    ) -> None:
        self._lectures = lectures
        self._queue = queue
        self._exports = exports
        self._revealer = revealer

    def status(self, lecture_id: str) -> ExportStatus:
        lecture = self._lecture(lecture_id)
        jobs = self._latest_jobs(lecture_id)
        return ExportStatus(
            directory=self._exports.directory(lecture.title),
            shared_with_other_lectures=self._is_shared(lecture),
            premiere=ExportFileStatus(
                file=self._exports.locate(lecture.title, PREMIERE_SUFFIX),
                job=jobs.get(JobKind.EXPORT_PREMIERE),
            ),
            mp4=ExportFileStatus(
                file=self._exports.locate(lecture.title, MP4_SUFFIX),
                job=jobs.get(JobKind.EXPORT_MP4),
            ),
        )

    def reveal(self, lecture_id: str) -> RevealTarget:
        """書き出したファイルのうち新しいほうを、Finder で選んで見せる。なければフォルダを見せる。

        見せる場所はレクチャーから求める（呼ぶ側からパスを受け取らない）。フォルダは作らない。
        """
        lecture = self._lecture(lecture_id)
        try:
            directory = self._exports.existing_directory(lecture.title)
        except ValueError as e:
            raise InvalidInputError(_DESTINATION_REFUSED) from e
        if directory is None:
            raise InvalidInputError(_NOTHING_EXPORTED)
        written = [
            (located.exported_at, located.path.name)
            for located in (self._exports.locate(lecture.title, suffix) for suffix in _SUFFIXES)
            if located.exported_at is not None
        ]
        if not written:
            self._revealer.reveal(directory)
            return RevealTarget.DIRECTORY
        _, newest = max(written)
        self._revealer.reveal(directory / newest)
        return RevealTarget.FILE

    def _lecture(self, lecture_id: str) -> Lecture:
        lecture = self._lectures.get(lecture_id)
        if lecture is None:
            raise NotFoundError(f"レクチャーがありません: {lecture_id}")
        return lecture

    def _latest_jobs(self, lecture_id: str) -> dict[JobKind, JobView]:
        latest: dict[JobKind, JobView] = {}
        for stored in self._queue.list_all():  # 登録順なので、後のものが残る
            job = stored.job
            if job.target_id == lecture_id and job.kind in EXPORT_KINDS:
                latest[job.kind] = JobView.of(job)
        return latest

    def _is_shared(self, lecture: Lecture) -> bool:
        place = self._place(lecture)
        return any(
            other.id != lecture.id and self._place(other) == place
            for other in self._lectures.list_all()
        )

    def _place(self, lecture: Lecture) -> str:
        # macOS の既定のボリュームは大文字と小文字を区別しないので、区別せずに比べる
        return str(self._exports.directory(lecture.title)).casefold()
