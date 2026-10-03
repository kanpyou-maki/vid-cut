"""依存の組み立て。ports に具象 adapters を注入する唯一の場所（ARCHITECTURE.md）。"""

import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from vidcut.adapters.claude_cli import ClaudeCli
from vidcut.adapters.media.tool import FfmpegMediaTool
from vidcut.adapters.ml.aligner import WhisperxAligner
from vidcut.adapters.ml.transcriber import MlxWhisperTranscriber
from vidcut.adapters.ml.vad import SileroVad
from vidcut.adapters.sqlite.database import open_database
from vidcut.adapters.sqlite.edit_states import SqliteEditStateRepository
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.adapters.sqlite.judgements import SqliteJudgementRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.adapters.workspace import FileArtifactStore, file_fingerprint
from vidcut.domain.models import Job, JobKind
from vidcut.jobs.worker import JobHandler, Worker
from vidcut.pipeline.analysis import AnalysisSettings, AnalysisTools
from vidcut.pipeline.judge import JudgeSettings
from vidcut.pipeline.ports import (
    Aligner,
    JobQueue,
    JudgementRepository,
    LanguageModel,
    LectureRepository,
    MediaTool,
    ProgressReporter,
    Transcriber,
    VoiceActivityDetector,
)
from vidcut.services.analysis import AnalysisService
from vidcut.services.imports import ImportService
from vidcut.services.judge import JudgeService
from vidcut.services.judge_eval import JudgeEvalService

DATABASE_FILE = "vidcut.sqlite3"
JUDGE_DIRECTORY = "judge"


def workspace_from_env(env: Mapping[str, str] = os.environ) -> Path:
    """ワークスペースは既定で ~/VidCut/。環境変数 VIDCUT_WORKSPACE で変えられる（ADR-004）。"""
    configured = env.get("VIDCUT_WORKSPACE")
    return Path(configured).expanduser() if configured else Path.home() / "VidCut"


def judge_workdir(workspace: Path) -> Path:
    """`claude -p` の作業ディレクトリ。開発用の設定が混ざらないよう、ワークスペース内に置く。"""
    return workspace / JUDGE_DIRECTORY


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
    lectures: LectureRepository
    judgements: JudgementRepository
    imports: ImportService
    analysis: AnalysisService
    judge: JudgeService
    judge_eval: JudgeEvalService
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
    model: LanguageModel | None = None,
    settings: AnalysisSettings | None = None,
    judge_settings: JudgeSettings | None = None,
) -> App:
    """media / ml / model はテストや E2E で偽の実装に差し替えるための引数。"""
    conn = open_database(workspace / DATABASE_FILE)
    media_tool = media or FfmpegMediaTool()
    ml_tools = ml or default_ml_tools()
    language_model = model or ClaudeCli(judge_workdir(workspace))
    recordings = SqliteRecordingRepository(conn)
    lectures = SqliteLectureRepository(conn)
    judgements = SqliteJudgementRepository(conn)
    queue = SqliteJobQueue(conn)
    store = FileArtifactStore(workspace)
    analysis = AnalysisService(
        recordings,
        AnalysisTools(
            media=media_tool,
            vad=ml_tools.vad,
            transcriber=ml_tools.transcriber,
            aligner=ml_tools.aligner,
            store=store,
        ),
        settings or AnalysisSettings(),
    )
    imports = ImportService(
        recordings=recordings,
        lectures=lectures,
        queue=queue,
        media=media_tool,
        fingerprint=file_fingerprint,
    )
    judge = JudgeService(
        lectures=lectures,
        store=store,
        judgements=judgements,
        edit_states=SqliteEditStateRepository(conn),
        queue=queue,
        model=language_model,
        settings=judge_settings or JudgeSettings(),
    )
    judge_eval = JudgeEvalService(
        lectures=lectures,
        store=store,
        model=language_model,
        settings=judge_settings or JudgeSettings(),
    )

    def analyze(job: Job, report: ProgressReporter) -> None:
        analysis.analyze(job.target_id, report)
        # レクチャーの全ファイルの解析がそろったら、言い直しの判定を積む
        judge.request_for_recording(job.target_id)

    handlers: dict[JobKind, JobHandler] = {
        JobKind.ANALYZE_RECORDING: analyze,
        JobKind.MAKE_MEZZANINE: lambda job, report: analysis.make_mezzanine(job.target_id, report),
        JobKind.JUDGE_LECTURE: lambda job, report: judge.judge(job.target_id, report),
    }
    return App(
        workspace=workspace,
        conn=conn,
        queue=queue,
        lectures=lectures,
        judgements=judgements,
        imports=imports,
        analysis=analysis,
        judge=judge,
        judge_eval=judge_eval,
        handlers=handlers,
    )
