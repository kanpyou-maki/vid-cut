from pathlib import Path

import pytest

from tests.pipeline.fakes import DirectoryStore, NoRecordings, make_recording
from vidcut.domain.models import Recording
from vidcut.pipeline.ports import NotFoundError, Peaks
from vidcut.services.recording_artifacts import RecordingArtifacts


class OneRecording(NoRecordings):
    """r1 だけが登録されている RecordingRepository。"""

    def __init__(self, source: Path) -> None:
        self._recording = make_recording(source, "r1")

    def get(self, recording_id: str) -> Recording | None:
        return self._recording if recording_id == "r1" else None


@pytest.fixture
def store(tmp_path: Path) -> DirectoryStore:
    return DirectoryStore(tmp_path / "ws")


@pytest.fixture
def artifacts(tmp_path: Path, store: DirectoryStore) -> RecordingArtifacts:
    return RecordingArtifacts(recordings=OneRecording(tmp_path / "r1.mov"), store=store)


class TestProxyPath:
    def test_returns_the_proxy_video(
        self, artifacts: RecordingArtifacts, store: DirectoryStore
    ) -> None:
        store.path("r1", "proxy.mp4").write_bytes(b"proxy")
        assert artifacts.proxy_path("r1") == store.path("r1", "proxy.mp4")

    def test_proxy_not_made_yet(self, artifacts: RecordingArtifacts) -> None:
        with pytest.raises(NotFoundError, match="プレビュー"):
            artifacts.proxy_path("r1")

    def test_unknown_recording_creates_no_directory(
        self, artifacts: RecordingArtifacts, store: DirectoryStore
    ) -> None:
        with pytest.raises(NotFoundError, match="登録されていません"):
            artifacts.proxy_path("nope")
        assert not (store.root / "nope").exists()


class TestPeaks:
    def test_returns_the_waveform_peaks(
        self, artifacts: RecordingArtifacts, store: DirectoryStore
    ) -> None:
        store.write_json("r1", "peaks.json", {"per_second": 100, "values": [0, 0.5, 1.0]})
        assert artifacts.peaks("r1") == Peaks(per_second=100, values=(0.0, 0.5, 1.0))

    def test_peaks_not_made_yet(self, artifacts: RecordingArtifacts) -> None:
        with pytest.raises(NotFoundError, match="ピーク値"):
            artifacts.peaks("r1")

    def test_unknown_recording(self, artifacts: RecordingArtifacts) -> None:
        with pytest.raises(NotFoundError, match="登録されていません"):
            artifacts.peaks("nope")

    @pytest.mark.parametrize(
        "data",
        [
            {},
            {"per_second": 100},
            {"per_second": "100", "values": []},
            {"per_second": 0, "values": []},
            {"per_second": 100, "values": ["x"]},
            {"per_second": 100, "values": 1},
            [],
        ],
    )
    def test_unreadable_peaks(
        self, artifacts: RecordingArtifacts, store: DirectoryStore, data: object
    ) -> None:
        store.write_json("r1", "peaks.json", data)
        with pytest.raises(ValueError, match="生成物の形が不正"):
            artifacts.peaks("r1")
