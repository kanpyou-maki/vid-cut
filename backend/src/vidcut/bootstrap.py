"""依存の組み立て。ports に具象 adapters を注入する唯一の場所（ARCHITECTURE.md）。"""

import os
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path

from vidcut.adapters.claude_cli import ClaudeCli
from vidcut.adapters.media.commands import MediaSettings
from vidcut.adapters.media.tool import FfmpegMediaTool
from vidcut.adapters.ml.aligner import WhisperxAligner
from vidcut.adapters.ml.transcriber import MlxWhisperTranscriber
from vidcut.adapters.ml.vad import SileroVad
from vidcut.adapters.sqlite.database import connect_database, open_database, transaction
from vidcut.adapters.sqlite.edit_states import SqliteEditStateRepository
from vidcut.adapters.sqlite.jobs import SqliteJobQueue
from vidcut.adapters.sqlite.judgements import SqliteJudgementRepository
from vidcut.adapters.sqlite.lectures import SqliteLectureRepository
from vidcut.adapters.sqlite.recordings import SqliteRecordingRepository
from vidcut.adapters.workspace import FileArtifactStore, FileExportStore, file_fingerprint
from vidcut.domain.models import Job, JobKind
from vidcut.jobs.worker import JobHandler, Worker
from vidcut.pipeline.analysis import AnalysisSettings, AnalysisTools
from vidcut.pipeline.export import ExportSettings
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
from vidcut.services.edits import EditService
from vidcut.services.export import ExportService
from vidcut.services.imports import ImportService
from vidcut.services.job_control import JobControl
from vidcut.services.judge import JudgeRequests, JudgeService
from vidcut.services.judge_eval import JudgeEvalService
from vidcut.services.lecture_views import LectureQuery
from vidcut.services.lectures import LectureService
from vidcut.services.recording_artifacts import RecordingArtifacts

DATABASE_FILE = "vidcut.sqlite3"
JUDGE_DIRECTORY = "judge"


def workspace_from_env(env: Mapping[str, str] = os.environ) -> Path:
    """ワークスペースは既定で ~/VidCut/。環境変数 VIDCUT_WORKSPACE で変えられる（ADR-004）。"""
    configured = env.get("VIDCUT_WORKSPACE")
    return Path(configured).expanduser() if configured else Path.home() / "VidCut"


def media_settings_for(export_settings: ExportSettings) -> MediaSettings:
    """中間素材のフレームレートを書き出しと同じにする（食い違うとカット点がずれる。ADR-002）。"""
    return MediaSettings(mezzanine_fps=export_settings.fps)


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
class _Stores:
    """1 本の接続の上のリポジトリとジョブ表、ワークスペースの生成物。"""

    conn: sqlite3.Connection
    recordings: SqliteRecordingRepository
    lectures: SqliteLectureRepository
    judgements: SqliteJudgementRepository
    edit_states: SqliteEditStateRepository
    queue: SqliteJobQueue
    store: FileArtifactStore

    def atomic(self) -> AbstractContextManager[None]:
        # リポジトリはすべて同じ接続を使うので、この接続のトランザクションでまとめられる
        return transaction(self.conn)


def _stores(conn: sqlite3.Connection, workspace: Path) -> _Stores:
    return _Stores(
        conn=conn,
        recordings=SqliteRecordingRepository(conn),
        lectures=SqliteLectureRepository(conn),
        judgements=SqliteJudgementRepository(conn),
        edit_states=SqliteEditStateRepository(conn),
        queue=SqliteJobQueue(conn),
        store=FileArtifactStore(workspace),
    )


@dataclass(frozen=True)
class ApiServices:
    """API の 1 リクエストが使う services。接続はこのリクエストだけのもの（Design Doc 3-5-2）。

    ML のモデルと言語モデルは持たない（解析と判定は worker プロセスが行う）。
    exports は依頼（request）だけに使う。
    export_settings は、書き出しが残す区間の余白を画面に伝えるために持つ
    （プレビューが、書き出しと同じ区間を残す）。
    """

    conn: sqlite3.Connection
    export_settings: ExportSettings
    imports: ImportService
    lecture_service: LectureService
    lecture_views: LectureQuery
    edits: EditService
    exports: ExportService
    jobs: JobControl
    artifacts: RecordingArtifacts


def _api_services(
    stores: _Stores, workspace: Path, media: MediaTool, export_settings: ExportSettings
) -> ApiServices:
    judge_requests = JudgeRequests(lectures=stores.lectures, store=stores.store, queue=stores.queue)
    return ApiServices(
        conn=stores.conn,
        export_settings=export_settings,
        jobs=JobControl(stores.queue),
        artifacts=RecordingArtifacts(recordings=stores.recordings, store=stores.store),
        imports=ImportService(
            recordings=stores.recordings,
            lectures=stores.lectures,
            queue=stores.queue,
            media=media,
            fingerprint=file_fingerprint,
        ),
        lecture_service=LectureService(
            lectures=stores.lectures,
            recordings=stores.recordings,
            edit_states=stores.edit_states,
            judgements=stores.judgements,
            store=stores.store,
            queue=stores.queue,
            atomic=stores.atomic,
            request_judge=judge_requests.for_recording,
        ),
        lecture_views=LectureQuery(
            lectures=stores.lectures,
            recordings=stores.recordings,
            edit_states=stores.edit_states,
            judgements=stores.judgements,
            store=stores.store,
            queue=stores.queue,
        ),
        edits=EditService(
            lectures=stores.lectures,
            recordings=stores.recordings,
            edit_states=stores.edit_states,
            judgements=stores.judgements,
        ),
        exports=ExportService(
            lectures=stores.lectures,
            recordings=stores.recordings,
            store=stores.store,
            judgements=stores.judgements,
            edit_states=stores.edit_states,
            queue=stores.queue,
            media=media,
            exports=FileExportStore(workspace),
            settings=export_settings,
        ),
    )


@dataclass(frozen=True)
class Api:
    """API サーバーの組み立て。services() をリクエストごとに呼ぶ。"""

    workspace: Path
    media: MediaTool
    export_settings: ExportSettings

    @contextmanager
    def services(self) -> Iterator[ApiServices]:
        """このリクエストだけの接続を開き、終わったら閉じる。

        FastAPI は依存の準備と本体を別のスレッドで動かすことがあるので、接続はスレッドに縛らない。
        1 つのリクエストの中では直列に使う。
        """
        conn = connect_database(self.workspace / DATABASE_FILE, check_same_thread=False)
        try:
            yield _api_services(
                _stores(conn, self.workspace), self.workspace, self.media, self.export_settings
            )
        finally:
            conn.close()


def build_api(
    workspace: Path,
    *,
    media: MediaTool | None = None,
    export_settings: ExportSettings | None = None,
) -> Api:
    """API サーバーの起動時に 1 回呼ぶ。スキーマの移行はここで済ませる。"""
    open_database(workspace / DATABASE_FILE).close()
    resolved_export_settings = export_settings or ExportSettings()
    return Api(
        workspace=workspace,
        media=media or FfmpegMediaTool(settings=media_settings_for(resolved_export_settings)),
        export_settings=resolved_export_settings,
    )


@dataclass(frozen=True)
class App:
    """worker と CLI の組み立て。接続を 1 本持ち、解析・判定・書き出しの本体も動かせる。"""

    workspace: Path
    conn: sqlite3.Connection
    queue: JobQueue
    lectures: LectureRepository
    judgements: JudgementRepository
    imports: ImportService
    analysis: AnalysisService
    judge: JudgeService
    judge_eval: JudgeEvalService
    lecture_service: LectureService
    lecture_views: LectureQuery
    edits: EditService
    exports: ExportService
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
    export_settings: ExportSettings | None = None,
) -> App:
    """media / ml / model はテストや E2E で偽の実装に差し替えるための引数。"""
    stores = _stores(open_database(workspace / DATABASE_FILE), workspace)
    resolved_export_settings = export_settings or ExportSettings()
    media_tool = media or FfmpegMediaTool(settings=media_settings_for(resolved_export_settings))
    shared = _api_services(stores, workspace, media_tool, resolved_export_settings)
    analysis = _analysis_service(stores, media_tool, ml or default_ml_tools(), settings)
    judge, judge_eval = _judge_services(
        stores, model or ClaudeCli(judge_workdir(workspace)), judge_settings or JudgeSettings()
    )
    return App(
        workspace=workspace,
        conn=stores.conn,
        queue=stores.queue,
        lectures=stores.lectures,
        judgements=stores.judgements,
        imports=shared.imports,
        analysis=analysis,
        judge=judge,
        judge_eval=judge_eval,
        lecture_service=shared.lecture_service,
        lecture_views=shared.lecture_views,
        edits=shared.edits,
        exports=shared.exports,
        handlers=_job_handlers(analysis, judge, shared.exports),
    )


def _analysis_service(
    stores: _Stores, media: MediaTool, ml: MlTools, settings: AnalysisSettings | None
) -> AnalysisService:
    tools = AnalysisTools(
        media=media,
        vad=ml.vad,
        transcriber=ml.transcriber,
        aligner=ml.aligner,
        store=stores.store,
    )
    return AnalysisService(stores.recordings, tools, settings or AnalysisSettings())


def _judge_services(
    stores: _Stores, model: LanguageModel, settings: JudgeSettings
) -> tuple[JudgeService, JudgeEvalService]:
    """判定の本体と、その精度評価。どちらも言語モデルを使う（worker と CLI だけが持つ）。"""
    judge = JudgeService(
        lectures=stores.lectures,
        store=stores.store,
        judgements=stores.judgements,
        edit_states=stores.edit_states,
        atomic=stores.atomic,
        queue=stores.queue,
        model=model,
        settings=settings,
    )
    judge_eval = JudgeEvalService(
        lectures=stores.lectures, store=stores.store, model=model, settings=settings
    )
    return judge, judge_eval


def _job_handlers(
    analysis: AnalysisService, judge: JudgeService, exports: ExportService
) -> dict[JobKind, JobHandler]:
    def analyze(job: Job, report: ProgressReporter) -> None:
        analysis.analyze(job.target_id, report)
        # レクチャーの全ファイルの解析がそろったら、言い直しの判定を積む。
        # 積めなかったときは解析ジョブを失敗にする（黙って判定が抜けるより、再実行できるほうがよい。
        # 解析は生成物のキャッシュがあるので、再実行はすぐ終わる）
        judge.request_for_recording(job.target_id)

    return {
        JobKind.ANALYZE_RECORDING: analyze,
        JobKind.MAKE_MEZZANINE: lambda job, report: analysis.make_mezzanine(job.target_id, report),
        JobKind.JUDGE_LECTURE: lambda job, report: judge.judge(job.target_id, report),
        JobKind.EXPORT_PREMIERE: lambda job, report: exports.export_premiere(job.target_id, report),
        JobKind.EXPORT_MP4: lambda job, report: exports.export_mp4(job.target_id, report),
    }
