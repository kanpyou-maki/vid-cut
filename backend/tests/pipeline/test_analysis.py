from dataclasses import replace
from pathlib import Path

import pytest

from tests.pipeline.fakes import (
    DirectoryStore,
    FakeAligner,
    FakeMediaTool,
    FakeTranscriber,
    FakeVad,
    make_recording,
)
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, Recording, ReviewMarkKind
from vidcut.pipeline.analysis import (
    AnalysisSettings,
    AnalysisTools,
    analyze_recording,
    load_analysis,
)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "lecture.mov"
    path.write_bytes(b"mov")
    return path


@pytest.fixture
def recording(source: Path) -> Recording:
    return make_recording(source)


@pytest.fixture
def tools(tmp_path: Path) -> AnalysisTools:
    return AnalysisTools(
        media=FakeMediaTool(),
        vad=FakeVad(),
        transcriber=FakeTranscriber(),
        aligner=FakeAligner(),
        store=DirectoryStore(tmp_path / "workspace"),
    )


def run(
    recording: Recording, tools: AnalysisTools, settings: AnalysisSettings | None = None
) -> list[tuple[str | None, float]]:
    reported: list[tuple[str | None, float]] = []
    analyze_recording(
        recording,
        tools,
        settings or AnalysisSettings(),
        lambda stage, progress: reported.append((stage, progress)),
    )
    return reported


def counts(tools: AnalysisTools) -> dict[str, int]:
    media = tools.media
    assert isinstance(media, FakeMediaTool)
    assert isinstance(tools.vad, FakeVad)
    assert isinstance(tools.transcriber, FakeTranscriber)
    assert isinstance(tools.aligner, FakeAligner)
    return {
        "audio": media.calls["extract_audio"],
        "proxy": media.calls["make_proxy"],
        "silence": media.calls["detect_silences"],
        "vad": tools.vad.calls,
        "transcribe": tools.transcriber.calls,
        "align": tools.aligner.calls,
    }


class TestAnalyzeRecording:
    def test_produces_chunks_tokens_and_suggestions(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        analysis = analyze_recording(recording, tools, AnalysisSettings(), lambda s, p: None)
        assert [c.span for c in analysis.chunks] == [Interval(1_000, 4_000), Interval(5_000, 9_000)]
        assert "".join(t.text for t in analysis.tokens) == "えーとこんにちは"
        silences = [s for s in analysis.suggestions if s.kind is CutKind.SILENCE]
        assert [s.span for s in silences] == [s.span for s in analysis.silences]
        assert len(silences) == 3
        (filler,) = [s for s in analysis.suggestions if s.kind is CutKind.FILLER]
        assert filler.span == Interval(1_000, 1_300)

    def test_suggestion_ids_are_unique_across_recordings(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        analysis = analyze_recording(recording, tools, AnalysisSettings(), lambda s, p: None)
        ids = [s.id for s in analysis.suggestions]
        assert len(set(ids)) == len(ids)
        assert all(sid.startswith(f"{recording.id}-") for sid in ids)

    def test_marks_low_confidence_and_unrecognized_speech(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        analysis = analyze_recording(recording, tools, AnalysisSettings(), lambda s, p: None)
        assert [(m.kind, m.span) for m in analysis.review_marks] == [
            (ReviewMarkKind.LOW_CONFIDENCE, Interval(5_000, 9_000)),
            (ReviewMarkKind.UNRECOGNIZED_SPEECH, Interval(6_500, 8_500)),
        ]

    def test_writes_proxy_peaks_and_result(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        analysis = analyze_recording(recording, tools, AnalysisSettings(), lambda s, p: None)
        store = tools.store
        assert store.path(recording.id, "proxy.mp4").exists()
        assert store.read_json(recording.id, "peaks.json") == {
            "per_second": 100,
            "values": [0.0, 0.5, 1.0],
        }
        assert load_analysis(store, recording.id) == analysis

    def test_passes_filler_hint_to_transcriber(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        run(recording, tools)
        assert isinstance(tools.transcriber, FakeTranscriber)
        assert "えー" in tools.transcriber.hints[0]

    def test_reports_stages_with_increasing_progress(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        reported = run(recording, tools)
        progress = [p for _, p in reported]
        assert progress == sorted(progress)
        assert progress[0] >= 0.0
        assert progress[-1] == 1.0
        assert {"audio", "silence", "proxy", "transcribe", "align"} <= {s for s, _ in reported}


class TestResume:
    def test_second_run_reuses_every_stage(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        run(recording, tools)
        run(recording, tools)
        assert set(counts(tools).values()) == {1}

    def test_changed_setting_redoes_only_dependent_stages(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        run(recording, tools)
        run(recording, tools, replace(AnalysisSettings(), silence_min_ms=500))
        assert counts(tools) == {
            "audio": 1,
            "proxy": 1,
            "silence": 2,
            "vad": 2,
            "transcribe": 2,
            "align": 2,
        }

    def test_changed_model_redoes_transcription_and_alignment(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        run(recording, tools)
        assert isinstance(tools.transcriber, FakeTranscriber)
        tools.transcriber.model_id = "other-model"
        run(recording, tools)
        assert counts(tools)["transcribe"] == 2
        assert counts(tools)["align"] == 2
        assert counts(tools)["silence"] == 1

    def test_changed_alignment_model_redoes_only_alignment(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        run(recording, tools)
        assert isinstance(tools.aligner, FakeAligner)
        tools.aligner.model_id = "other-aligner"
        run(recording, tools)
        assert counts(tools)["transcribe"] == 1
        assert counts(tools)["align"] == 2

    def test_deleted_file_is_regenerated(self, recording: Recording, tools: AnalysisTools) -> None:
        run(recording, tools)
        tools.store.path(recording.id, "proxy.mp4").unlink()
        run(recording, tools)
        assert counts(tools)["proxy"] == 2
        assert counts(tools)["transcribe"] == 1

    def test_changed_source_file_redoes_everything(
        self, recording: Recording, tools: AnalysisTools
    ) -> None:
        run(recording, tools)
        run(replace(recording, fingerprint="changed"), tools)
        assert set(counts(tools).values()) == {2}


def test_missing_source_file_is_reported(recording: Recording, tools: AnalysisTools) -> None:
    Path(recording.source_path).unlink()
    with pytest.raises(FileNotFoundError, match="録画ファイル"):
        run(recording, tools)


def test_load_analysis_without_result_is_none(tools: AnalysisTools) -> None:
    assert load_analysis(tools.store, "never-analyzed") is None


def test_corrupted_artifact_is_recomputed(recording: Recording, tools: AnalysisTools) -> None:
    run(recording, tools)
    tools.store.write_json(recording.id, "transcript.raw.json", [{"broken": True}])
    analysis = analyze_recording(recording, tools, AnalysisSettings(), lambda s, p: None)
    assert counts(tools)["transcribe"] == 2
    assert "".join(t.text for t in analysis.tokens) == "えーとこんにちは"


def test_broken_result_file_is_an_error(recording: Recording, tools: AnalysisTools) -> None:
    tools.store.write_json(recording.id, "analysis.json", {"chunks": "x"})
    with pytest.raises(ValueError, match="形が不正"):
        load_analysis(tools.store, recording.id)


def test_broken_stage_manifest_redoes_everything(
    recording: Recording, tools: AnalysisTools
) -> None:
    run(recording, tools)
    tools.store.path(recording.id, "stages.json").write_text("{broken")
    run(recording, tools)
    assert counts(tools)["transcribe"] == 2


def test_recording_without_speech_has_no_chunks(recording: Recording, tools: AnalysisTools) -> None:
    assert isinstance(tools.media, FakeMediaTool)
    assert isinstance(tools.vad, FakeVad)
    tools.media.silences = (Interval(0, 10_000),)
    tools.vad.speech = ()
    analysis = analyze_recording(recording, tools, AnalysisSettings(), lambda s, p: None)
    assert analysis.chunks == ()
    assert analysis.tokens == ()
    assert [s.span for s in analysis.suggestions] == [Interval(0, 10_000)]


def test_failure_keeps_finished_stages_for_the_retry(
    recording: Recording, tools: AnalysisTools
) -> None:
    assert isinstance(tools.transcriber, FakeTranscriber)
    tools.transcriber.error = RuntimeError("model crashed")
    with pytest.raises(RuntimeError):
        run(recording, tools)
    assert load_analysis(tools.store, recording.id) is None
    tools.transcriber.error = None
    run(recording, tools)
    assert counts(tools)["audio"] == 1
    assert counts(tools)["proxy"] == 1
    assert counts(tools)["transcribe"] == 2


def test_transcript_with_wrong_number_of_chunks_is_recomputed(
    recording: Recording, tools: AnalysisTools
) -> None:
    run(recording, tools)
    tools.store.write_json(recording.id, "transcript.raw.json", [])
    run(recording, tools)
    assert counts(tools)["transcribe"] == 2
