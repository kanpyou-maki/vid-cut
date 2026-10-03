"""解析と中間素材のジョブの本体（ジョブ analyze_recording / make_mezzanine）。"""

from pathlib import Path

from vidcut.domain.models import Recording
from vidcut.pipeline.analysis import Analysis, AnalysisSettings, AnalysisTools, analyze_recording
from vidcut.pipeline.mezzanine import make_mezzanine
from vidcut.pipeline.ports import (
    ArtifactStore,
    NotFoundError,
    ProgressReporter,
    RecordingRepository,
)


class AnalysisService:
    def __init__(
        self, recordings: RecordingRepository, tools: AnalysisTools, settings: AnalysisSettings
    ) -> None:
        self._recordings = recordings
        self._tools = tools
        self._settings = settings

    @property
    def store(self) -> ArtifactStore:
        return self._tools.store

    def analyze(self, recording_id: str, report: ProgressReporter) -> Analysis:
        return analyze_recording(self._get(recording_id), self._tools, self._settings, report)

    def make_mezzanine(self, recording_id: str, report: ProgressReporter) -> Path:
        return make_mezzanine(self._get(recording_id), self._tools.media, self.store, report)

    def _get(self, recording_id: str) -> Recording:
        recording = self._recordings.get(recording_id)
        if recording is None:
            raise NotFoundError(f"録画ファイルが登録されていません: {recording_id}")
        return recording
