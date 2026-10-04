"""解析と中間素材のジョブの本体（ジョブ analyze_recording / make_mezzanine）。"""

import logging
from collections.abc import Sequence
from pathlib import Path

from vidcut.domain.models import CutSuggestion, Recording
from vidcut.domain.overrides import carry_over_analysis_restorations
from vidcut.pipeline.analysis import Analysis, AnalysisSettings, AnalysisTools, analyze_recording
from vidcut.pipeline.analysis_result import load_analysis
from vidcut.pipeline.mezzanine import make_mezzanine
from vidcut.pipeline.ports import (
    ArtifactStore,
    EditStateRepository,
    LectureRepository,
    NotFoundError,
    ProgressReporter,
    RecordingRepository,
    VersionConflictError,
)

_SAVE_ATTEMPTS = 3  # 編集状態の保存が画面の保存と重なったら、読み直してやり直す

_logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(
        self,
        recordings: RecordingRepository,
        tools: AnalysisTools,
        settings: AnalysisSettings,
        *,
        lectures: LectureRepository,
        edit_states: EditStateRepository,
    ) -> None:
        self._recordings = recordings
        self._tools = tools
        self._settings = settings
        self._lectures = lectures
        self._edit_states = edit_states

    @property
    def store(self) -> ArtifactStore:
        return self._tools.store

    def analyze(self, recording_id: str, report: ProgressReporter) -> Analysis:
        """解析して保存する。解析し直しなら、戻していた無音・フィラーの候補を新しい候補へ引き継ぐ。"""
        recording = self._get(recording_id)
        previous = self._previous_suggestions(recording_id)
        analysis = analyze_recording(recording, self._tools, self._settings, report)
        if previous:
            self._carry_over_restorations(recording_id, previous, analysis.suggestions)
        return analysis

    def _previous_suggestions(self, recording_id: str) -> tuple[CutSuggestion, ...]:
        """解析し直す前の候補。初めての解析か、前の結果が読めなければ、なし。"""
        try:
            previous = load_analysis(self.store, recording_id)
        except ValueError:
            # 対応づける相手がない。戻していた無音・フィラーの id は、そのまま残る（既知の限界）
            _logger.warning(
                "前の解析結果を読めないため、戻した無音・フィラーを引き継げません: %s", recording_id
            )
            return ()
        return previous.suggestions if previous else ()

    def _carry_over_restorations(
        self, recording_id: str, old: Sequence[CutSuggestion], new: Sequence[CutSuggestion]
    ) -> None:
        lecture = self._lectures.find_by_recording(recording_id)
        if lecture is None:
            return
        for _ in range(_SAVE_ATTEMPTS):
            state = self._edit_states.get(lecture.id)
            carried = carry_over_analysis_restorations(state, old, new)
            if carried is state:
                return
            try:
                self._edit_states.save(carried)
            except VersionConflictError:
                continue
            _logger.info("戻した無音・フィラーの候補を、解析し直した結果へ引き継ぎました")
            return
        _logger.warning("編集状態の保存が重なり、戻した候補を引き継げませんでした: %s", lecture.id)

    def make_mezzanine(self, recording_id: str, report: ProgressReporter) -> Path:
        return make_mezzanine(self._get(recording_id), self._tools.media, self.store, report)

    def _get(self, recording_id: str) -> Recording:
        recording = self._recordings.get(recording_id)
        if recording is None:
            raise NotFoundError(f"録画ファイルが登録されていません: {recording_id}")
        return recording
