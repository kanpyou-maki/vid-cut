import json
from pathlib import Path

import pytest

from tests.e2e.script import LINES, RETAKE_REASON, ScriptedJudge, ScriptedTranscriber, SilentVad
from tests.pipeline.judge_fakes import make_analysis
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind
from vidcut.pipeline.judge import (
    JudgeSettings,
    build_entries,
    judge_entries,
    render_listing,
)

AUDIO = Path("audio.wav")
TEXTS = [line.text for line in LINES]


def _spans(count: int) -> list[Interval]:
    return [Interval(i * 2_000, i * 2_000 + 1_000) for i in range(count)]


class TestSilentVad:
    def test_reports_no_speech(self) -> None:
        assert SilentVad().detect_speech(AUDIO) == ()


class TestScriptedTranscriber:
    def test_returns_the_script_line_by_line(self) -> None:
        transcripts = ScriptedTranscriber().transcribe(
            AUDIO, _spans(len(LINES)), hint="", on_progress=None
        )

        assert [t.text for t in transcripts] == TEXTS

    def test_reports_progress(self) -> None:
        seen: list[float] = []

        ScriptedTranscriber().transcribe(
            AUDIO, _spans(len(LINES)), hint="", on_progress=seen.append
        )

        assert seen == [1.0]

    def test_rejects_a_material_that_does_not_match_the_script(self) -> None:
        with pytest.raises(ValueError, match="台本"):
            ScriptedTranscriber().transcribe(
                AUDIO, _spans(len(LINES) + 1), hint="", on_progress=None
            )

    def test_one_line_has_low_confidence(self) -> None:
        transcripts = ScriptedTranscriber().transcribe(
            AUDIO, _spans(len(LINES)), hint="", on_progress=None
        )

        assert sum(t.avg_logprob < -0.5 for t in transcripts) == 1


class TestScriptedJudge:
    def test_deletes_the_retake_and_points_to_the_next_chunk(self) -> None:
        entries = build_entries([make_analysis("r1", TEXTS)])

        decisions = judge_entries(ScriptedJudge(), entries, JudgeSettings())

        assert [(d.number, d.kind, d.reason, d.superseded_by) for d in decisions] == [
            (1, CutKind.RETAKE, RETAKE_REASON, 2)
        ]

    def test_judges_every_recording_of_a_lecture(self) -> None:
        entries = build_entries([make_analysis("r1", TEXTS), make_analysis("r2", TEXTS)])

        decisions = judge_entries(ScriptedJudge(), entries, JudgeSettings())

        assert [(d.number, d.superseded_by) for d in decisions] == [(1, 2), (5, 6)]

    def test_deletes_nothing_when_there_is_no_retake(self) -> None:
        listing = render_listing(build_entries([make_analysis("r1", ["こんにちは。"])]))

        assert json.loads(ScriptedJudge().complete(f"指示\n{listing}")) == {"delete": []}

    def test_rejects_a_prompt_without_the_listing(self) -> None:
        with pytest.raises(ValueError, match="一覧を読み取れません"):
            ScriptedJudge().complete("指示だけで、一覧がない")

    def test_does_not_delete_the_last_chunk_as_a_retake(self) -> None:
        # 言い直した後の版がなければ、消さない
        listing = render_listing(build_entries([make_analysis("r1", TEXTS[:2])]))

        assert json.loads(ScriptedJudge().complete(listing)) == {"delete": []}
