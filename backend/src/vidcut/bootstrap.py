"""依存の組み立て。ports に具象 adapters を注入する唯一の場所（ARCHITECTURE.md）。"""

import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from vidcut.adapters.media.tool import FfmpegMediaTool
from vidcut.adapters.ml.aligner import WhisperxAligner
from vidcut.adapters.ml.transcriber import MlxWhisperTranscriber
from vidcut.adapters.ml.vad import SileroVad
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.adapters.workspace import FileArtifactStore, file_fingerprint
from vidcut.domain.models import JobKind
from vidcut.jobs.worker import JobHandler, Worker
from vidcut.pipeline.analysis import AnalysisSettings, AnalysisTools
from vidcut.pipeline.ports import (
    Aligner,
    JobQueue,
    MediaTool,
    Transcriber,
    VoiceActivityDetector,
)
from vidcut.services.analysis import AnalysisService
from vidcut.services.imports import ImportService

DATABASE_FILE = "vidcut.sqlite3"


def workspace_from_env(env: Mapping[str, str] = os.environ) -> Path:
    """ワークスペースは既定で ~/VidCut/。環境変数 VIDCUT_WORKSPACE で変えられる（ADR-004）。"""
    configured = env.get("VIDCUT_WORKSPACE")
    return Path(configured).expanduser() if configured else Path.home() / "VidCut"


@dataclass(frozen=True)
class MlTools:
    vad: VoiceActivityDetector
    transcriber: Transcriber
    aligner: Aligner


def default_ml_tools() -> MlTools:
    """モデルは最初に使うときに読み込む（取り込みだけのコマンドを速く保つ）。"""
    return MlTools(vad=SileroVad(), transcriber=MlxWhisperTranscriber(), aligner=WhisperxAligner())


@dataclass(frozen=True)
class App:
    workspace: Path
    conn: sqlite3.Connection
    queue: JobQueue
    imports: ImportService
    analysis: AnalysisService
    handlers: Mapping[JobKind, JobHandler]

    def worker(self) -> Worker:
        return Worker(self.queue, self.handlers)

    def close(self) -> None:
        self.conn.close()


def build_app(
    workspace: Path,
    *,
    media: MediaTool | None = None,
    ml: MlTools | None = None,
    settings: AnalysisSettings | None = None,
) -> App:
    """media / ml はテストや E2E で偽の実装に差し替えるための引数。"""
    conn = open_database(workspace / DATABASE_FILE)
    media_tool = media or FfmpegMediaTool()
    ml_tools = ml or default_ml_tools()
    recordings = SqliteRecordingRepository(conn)
    queue = SqliteJobQueue(conn)
    analysis = AnalysisService(
        recordings,
        AnalysisTools(
            media=media_tool,
            vad=ml_tools.vad,
            transcriber=ml_tools.transcriber,
            aligner=ml_tools.aligner,
            store=FileArtifactStore(workspace),
        ),
        settings or AnalysisSettings(),
    )
    imports = ImportService(
        recordings=recordings,
        lectures=SqliteLectureRepository(conn),
        queue=queue,
        media=media_tool,
        fingerprint=file_fingerprint,
    )
    handlers: dict[JobKind, JobHandler] = {
        JobKind.ANALYZE_RECORDING: lambda job, report: analysis.analyze(job.target_id, report),
        JobKind.MAKE_MEZZANINE: lambda job, report: analysis.make_mezzanine(job.target_id, report),
    }
    return App(workspace, conn, queue, imports, analysis, handlers)
