from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from tests.pipeline.fakes import make_recording
from vidcut.domain.intervals import Interval
from vidcut.domain.models import (
    CutKind,
    CutSuggestion,
    EditState,
    ManualCut,
    Recording,
    Silence,
    Token,
)
from vidcut.domain.timeline import FrameRange
from vidcut.pipeline.analysis_result import Analysis
from vidcut.pipeline.export import (
    ExportClip,
    ExportSettings,
    mezzanine_frame_count,
    plan_export,
)

SOURCE = Path("/rec/lecture.mov")
NO_EDITS = EditState(lecture_id="l1", version=0)


def recording(rid: str = "r1", duration_ms: int = 10_000) -> Recording:
    return replace(make_recording(SOURCE, rid), duration_ms=duration_ms)


def suggestion(
    rid: str, start_ms: int, end_ms: int, kind: CutKind = CutKind.SILENCE, sid: str | None = None
) -> CutSuggestion:
    return CutSuggestion(
        id=sid or f"{rid}-{kind}-{start_ms}",
        recording_id=rid,
        span=Interval(start_ms, end_ms),
        kind=kind,
        reason="理由",
    )


def analysis(
    rid: str = "r1",
    suggestions: Sequence[CutSuggestion] = (),
    silences: Sequence[Interval] = (),
    tokens: Sequence[Token] = (),
) -> Analysis:
    return Analysis(
        recording_id=rid,
        silences=tuple(Silence(rid, span) for span in silences),
        chunks=(),
        tokens=tuple(tokens),
        suggestions=tuple(suggestions),
        review_marks=(),
    )


def token(start_ms: int, end_ms: int, text: str, rid: str = "r1") -> Token:
    return Token(
        id=f"{rid}-t{start_ms}",
        recording_id=rid,
        chunk_id=f"{rid}-c0000",
        text=text,
        span=Interval(start_ms, end_ms),
        asr_confidence=0.9,
        align_score=0.9,
    )


def clips(plan_clips: Sequence[ExportClip]) -> list[tuple[str, int, int]]:
    return [(c.recording_id, c.frames.start_frame, c.frames.end_frame) for c in plan_clips]


class TestPlanExport:
    def test_without_cuts_the_whole_recording_is_one_clip(self) -> None:
        plan = plan_export([recording()], [analysis()], (), NO_EDITS, ExportSettings())
        assert plan.fps == 60
        assert clips(plan.clips) == [("r1", 0, 600)]
        assert plan.total_frames == 600

    def test_cut_silence_keeps_padding_inside_the_silence(self) -> None:
        # 4〜5 秒の無音を削る。残す区間の後ろに 250ms、次の区間の前に 150ms の余白が残る
        silent = Interval(4_000, 5_000)
        cut = suggestion("r1", 4_000, 5_000)
        plan = plan_export(
            [recording()], [analysis("r1", [cut], [silent])], (), NO_EDITS, ExportSettings()
        )
        assert clips(plan.clips) == [("r1", 0, 255), ("r1", 291, 600)]
        assert plan.total_frames == 255 + 309

    def test_silence_after_a_sentence_keeps_the_longer_padding(self) -> None:
        # 無音の前の最後の文字が「。」なら、残す区間の後ろに 500ms の余白が残る
        silent = Interval(4_000, 5_000)
        cut = suggestion("r1", 4_000, 5_000)
        spoken = [token(3_800, 3_900, "す"), token(3_900, 3_920, "。")]
        plan = plan_export(
            [recording()], [analysis("r1", [cut], [silent], spoken)], (), NO_EDITS, ExportSettings()
        )
        assert clips(plan.clips) == [("r1", 0, 270), ("r1", 291, 600)]

    def test_silence_in_the_middle_of_a_sentence_keeps_the_usual_padding(self) -> None:
        silent = Interval(4_000, 5_000)
        cut = suggestion("r1", 4_000, 5_000)
        spoken = [token(3_800, 3_900, "が"), token(3_900, 3_920, "、")]
        plan = plan_export(
            [recording()], [analysis("r1", [cut], [silent], spoken)], (), NO_EDITS, ExportSettings()
        )
        assert clips(plan.clips) == [("r1", 0, 255), ("r1", 291, 600)]

    def test_sentence_padding_follows_the_tokens_of_each_recording(self) -> None:
        # 1 本目は「。」、2 本目は「、」で終わる。長い余白は 1 本目だけ
        silent = Interval(4_000, 5_000)
        parts = [
            analysis(
                rid, [suggestion(rid, 4_000, 5_000)], [silent], [token(3_900, 3_920, text, rid)]
            )
            for rid, text in (("r1", "。"), ("r2", "、"))
        ]
        plan = plan_export(
            [recording("r1"), recording("r2")], parts, (), NO_EDITS, ExportSettings()
        )
        assert clips(plan.clips) == [
            ("r1", 0, 270),
            ("r1", 291, 600),
            ("r2", 0, 255),
            ("r2", 291, 600),
        ]

    def test_sentence_padding_is_configurable(self) -> None:
        silent = Interval(4_000, 5_000)
        cut = suggestion("r1", 4_000, 5_000)
        spoken = [token(3_900, 3_920, "。")]
        settings = ExportSettings(pad_after_sentence_ms=800)
        plan = plan_export(
            [recording()], [analysis("r1", [cut], [silent], spoken)], (), NO_EDITS, settings
        )
        assert clips(plan.clips) == [("r1", 0, 288), ("r1", 291, 600)]

    def test_judged_retakes_are_cut_without_padding_into_speech(self) -> None:
        retake = suggestion("r1", 2_000, 3_000, CutKind.RETAKE)
        plan = plan_export([recording()], [analysis()], [retake], NO_EDITS, ExportSettings())
        assert clips(plan.clips) == [("r1", 0, 120), ("r1", 180, 600)]

    def test_restored_suggestions_are_kept(self) -> None:
        silence = suggestion("r1", 4_000, 5_000, sid="s1")
        retake = suggestion("r1", 2_000, 3_000, CutKind.RETAKE, sid="j1")
        state = EditState("l1", 3, restored_suggestion_ids=frozenset({"s1", "j1"}))
        plan = plan_export(
            [recording()], [analysis("r1", [silence])], [retake], state, ExportSettings()
        )
        assert clips(plan.clips) == [("r1", 0, 600)]

    def test_manual_cuts_are_removed(self) -> None:
        state = EditState("l1", 1, manual_cuts=(ManualCut("m1", "r1", Interval(0, 1_000)),))
        plan = plan_export([recording()], [analysis()], (), state, ExportSettings())
        assert clips(plan.clips) == [("r1", 60, 600)]

    def test_start_rounds_down_and_end_rounds_up_to_frames(self) -> None:
        # 1001ms は 60.06 フレーム、2001ms は 120.06 フレーム
        state = EditState("l1", 1, manual_cuts=(ManualCut("m1", "r1", Interval(1_001, 2_001)),))
        plan = plan_export([recording()], [analysis()], (), state, ExportSettings())
        assert clips(plan.clips) == [("r1", 0, 61), ("r1", 120, 600)]

    def test_recordings_follow_the_lecture_order(self) -> None:
        cut_r1 = suggestion("r1", 0, 1_000, CutKind.RETAKE)
        cut_r2 = suggestion("r2", 9_000, 10_000, CutKind.NOISE)
        plan = plan_export(
            [recording("r2"), recording("r1")],
            [analysis("r2"), analysis("r1")],
            [cut_r1, cut_r2],
            NO_EDITS,
            ExportSettings(),
        )
        assert clips(plan.clips) == [("r2", 0, 540), ("r1", 60, 600)]
        assert plan.total_frames == 1_080

    def test_fully_cut_recording_contributes_no_clip(self) -> None:
        whole = suggestion("r1", 0, 10_000, CutKind.RETAKE)
        plan = plan_export(
            [recording("r1"), recording("r2")],
            [analysis("r1"), analysis("r2")],
            [whole],
            NO_EDITS,
            ExportSettings(),
        )
        assert clips(plan.clips) == [("r2", 0, 600)]

    def test_everything_cut_gives_an_empty_plan(self) -> None:
        whole = suggestion("r1", 0, 10_000, CutKind.RETAKE)
        plan = plan_export([recording()], [analysis()], [whole], NO_EDITS, ExportSettings())
        assert plan.clips == ()
        assert plan.total_frames == 0

    def test_frame_rate_and_padding_are_configurable(self) -> None:
        silent = Interval(4_000, 5_000)
        cut = suggestion("r1", 4_000, 5_000)
        settings = ExportSettings(fps=30, pad_before_ms=0, pad_after_ms=100)
        plan = plan_export([recording()], [analysis("r1", [cut], [silent])], (), NO_EDITS, settings)
        assert plan.fps == 30
        assert clips(plan.clips) == [("r1", 0, 123), ("r1", 150, 300)]

    def test_last_clip_ends_at_the_last_frame_of_the_mezzanine(self) -> None:
        # 実素材の長さはフレームの境界にそろわない（368,977ms は 22138.62 フレーム）
        plan = plan_export(
            [recording(duration_ms=368_977)], [analysis()], (), NO_EDITS, ExportSettings()
        )
        last = plan.clips[-1].frames
        assert last == FrameRange(0, mezzanine_frame_count(368_977, 60))

    def test_analysis_of_another_recording_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="解析結果"):
            plan_export([recording("r1")], [analysis("r2")], (), NO_EDITS, ExportSettings())

    def test_missing_analysis_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="解析結果"):
            plan_export([recording("r1"), recording("r2")], [analysis("r1")], (), NO_EDITS,
                        ExportSettings())  # fmt: skip


class TestExportSettings:
    @pytest.mark.parametrize("fps", [0, -1])
    def test_rejects_non_positive_frame_rate(self, fps: int) -> None:
        with pytest.raises(ValueError):
            ExportSettings(fps=fps)

    def test_sentence_padding_defaults_to_half_a_second(self) -> None:
        assert ExportSettings().pad_after_sentence_ms == 500

    def test_rejects_negative_sentence_padding(self) -> None:
        with pytest.raises(ValueError, match="余白"):
            ExportSettings(pad_after_sentence_ms=-1)

    def test_rejects_negative_padding(self) -> None:
        with pytest.raises(ValueError):
            ExportSettings(pad_before_ms=-1)


class TestMezzanineFrameCount:
    @pytest.mark.parametrize(
        ("duration_ms", "fps", "frames"),
        [(30_000, 60, 1_800), (368_977, 60, 22_139), (4_050, 60, 243), (1_001, 30, 31)],
    )
    def test_counts_frames_that_start_before_the_end(
        self, duration_ms: int, fps: int, frames: int
    ) -> None:
        assert mezzanine_frame_count(duration_ms, fps) == frames
