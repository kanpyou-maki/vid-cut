import pytest

from vidcut.domain.intervals import Interval
from vidcut.domain.models import (
    CutKind,
    CutSuggestion,
    EditState,
    Job,
    JobKind,
    JobStatus,
    Lecture,
    ManualCut,
    MediaInfo,
    Recording,
    Token,
)


def make_suggestion(sid: str = "s1", kind: CutKind = CutKind.SILENCE) -> CutSuggestion:
    return CutSuggestion(id=sid, recording_id="r1", span=Interval(0, 500), kind=kind, reason="")


class TestMediaInfoAndRecording:
    def test_rejects_non_positive_dimensions_and_rates(self) -> None:
        with pytest.raises(ValueError):
            MediaInfo(width=0, height=1080, is_vfr=True, avg_fps=3.2, audio_rate=48000)
        with pytest.raises(ValueError):
            MediaInfo(width=1920, height=1080, is_vfr=True, avg_fps=0, audio_rate=48000)

    def test_accepts_valid_recording(self) -> None:
        media = MediaInfo(width=3104, height=1964, is_vfr=True, avg_fps=3.2, audio_rate=48000)
        recording = Recording(
            id="r1",
            source_path="/a.mov",
            fingerprint="f",
            duration_ms=368_940,
            recorded_at=None,
            media=media,
        )
        assert recording.media.is_vfr

    def test_rejects_non_positive_duration(self) -> None:
        media = MediaInfo(width=1920, height=1080, is_vfr=False, avg_fps=60, audio_rate=48000)
        with pytest.raises(ValueError):
            Recording(
                id="r1",
                source_path="/a.mov",
                fingerprint="f",
                duration_ms=0,
                recorded_at=None,
                media=media,
            )


class TestToken:
    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_rejects_scores_outside_unit_range(self, value: float) -> None:
        with pytest.raises(ValueError):
            Token("t1", "r1", "c1", "あ", Interval(0, 10), asr_confidence=value, align_score=0.5)
        with pytest.raises(ValueError):
            Token("t1", "r1", "c1", "あ", Interval(0, 10), asr_confidence=0.5, align_score=value)

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(ValueError):
            Token("t1", "r1", "c1", "", Interval(0, 10), asr_confidence=0.5, align_score=0.5)


class TestLecture:
    def test_requires_at_least_one_recording(self) -> None:
        with pytest.raises(ValueError):
            Lecture(id="l1", title="t", recording_ids=())

    def test_rejects_duplicate_recordings(self) -> None:
        with pytest.raises(ValueError):
            Lecture(id="l1", title="t", recording_ids=("r1", "r1"))

    def test_reordered_returns_new_lecture_with_same_members(self) -> None:
        lecture = Lecture(id="l1", title="t", recording_ids=("r1", "r2"))
        reordered = lecture.reordered(("r2", "r1"))
        assert reordered.recording_ids == ("r2", "r1")
        assert lecture.recording_ids == ("r1", "r2")

    def test_reordered_rejects_different_members(self) -> None:
        lecture = Lecture(id="l1", title="t", recording_ids=("r1", "r2"))
        with pytest.raises(ValueError):
            lecture.reordered(("r1", "r3"))


class TestCutKind:
    def test_rejudged_kinds_are_those_from_retake_judgement(self) -> None:
        rejudged = {k for k in CutKind if k.is_rejudged}
        assert rejudged == {CutKind.RETAKE, CutKind.MISSPEAK, CutKind.NOISE}


class TestEditState:
    def test_restore_returns_new_state(self) -> None:
        state = EditState(lecture_id="l1", version=0)
        restored = state.restore("s1")
        assert restored.restored_suggestion_ids == frozenset({"s1"})
        assert state.restored_suggestion_ids == frozenset()

    def test_unrestore_removes_suggestion(self) -> None:
        state = EditState(lecture_id="l1", version=0).restore("s1").restore("s2")
        assert state.unrestore("s1").restored_suggestion_ids == frozenset({"s2"})

    def test_add_and_remove_manual_cut(self) -> None:
        cut = ManualCut(id="m1", recording_id="r1", span=Interval(100, 200))
        state = EditState(lecture_id="l1", version=0).add_manual_cut(cut)
        assert state.manual_cuts == (cut,)
        assert state.remove_manual_cut("m1").manual_cuts == ()

    def test_add_manual_cut_rejects_duplicate_id(self) -> None:
        cut = ManualCut(id="m1", recording_id="r1", span=Interval(100, 200))
        state = EditState(lecture_id="l1", version=0).add_manual_cut(cut)
        with pytest.raises(ValueError):
            state.add_manual_cut(cut)

    def test_rejects_negative_version(self) -> None:
        with pytest.raises(ValueError):
            EditState(lecture_id="l1", version=-1)


class TestJob:
    def test_rejects_progress_outside_unit_range(self) -> None:
        with pytest.raises(ValueError):
            Job(
                id="j1",
                kind=JobKind.ANALYZE_RECORDING,
                target_id="r1",
                status=JobStatus.RUNNING,
                progress=1.5,
            )

    def test_defaults_to_queued_without_error(self) -> None:
        job = Job(id="j1", kind=JobKind.JUDGE_LECTURE, target_id="l1")
        assert job.status is JobStatus.QUEUED
        assert job.progress == 0.0
        assert job.error is None


def test_cut_suggestion_requires_reason_for_retake() -> None:
    with pytest.raises(ValueError):
        make_suggestion(kind=CutKind.RETAKE)


@pytest.mark.parametrize("fps", [float("nan"), float("inf")])
def test_media_info_rejects_non_finite_fps(fps: float) -> None:
    with pytest.raises(ValueError):
        MediaInfo(width=1920, height=1080, is_vfr=True, avg_fps=fps, audio_rate=48000)
