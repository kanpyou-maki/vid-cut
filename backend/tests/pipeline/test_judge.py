import json
from collections.abc import Sequence

import pytest

from tests.pipeline.judge_fakes import FakeModel, delete_output, make_analysis
from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, CutSuggestion
from vidcut.pipeline.judge import (
    BOUNDARY_NOTE,
    MAX_REASON_CHARS,
    Decision,
    JudgeEntry,
    JudgeOutputError,
    JudgeSettings,
    Window,
    build_entries,
    input_key,
    judge_entries,
    load_prompt,
    parse_decisions,
    render_listing,
    split_windows,
    to_suggestions,
)


def entries_of(*texts: str, rid: str = "r1") -> tuple[JudgeEntry, ...]:
    return build_entries([make_analysis(rid, texts)])


def numbers(decisions: Sequence[Decision]) -> list[int]:
    return [d.number for d in decisions]


class TestLoadPrompt:
    def test_prompt_covers_kinds_and_file_boundary(self) -> None:
        prompt = load_prompt()
        for word in ("retake", "misspeak", "noise", "superseded_by", "録画ファイル"):
            assert word in prompt
        assert prompt.rstrip().endswith("チャンク一覧:")


class TestBuildEntries:
    def test_numbers_chunks_across_recordings_in_order(self) -> None:
        entries = build_entries(
            [make_analysis("r1", ("こんにちは", "えー")), make_analysis("r2", ("続きです",))]
        )
        assert [(e.number, e.chunk.recording_id, e.text) for e in entries] == [
            (0, "r1", "こんにちは"),
            (1, "r1", "えー"),
            (2, "r2", "続きです"),
        ]

    def test_chunk_without_text_is_not_judged_but_keeps_its_number(self) -> None:
        # 文字が割り当たらなかった発話は「未認識の発話」として人に回す（削除しない）
        entries = entries_of("はい", "", "次です")
        assert [(e.number, e.text) for e in entries] == [(0, "はい"), (2, "次です")]

    def test_no_recordings(self) -> None:
        assert build_entries([]) == ()


class TestRenderListing:
    def test_lists_number_seconds_and_text(self) -> None:
        listing = render_listing(entries_of("こんにちは", "えー"))
        assert listing.splitlines() == ["0\t0.0\t1.0\tこんにちは", "1\t2.0\t3.0\tえー"]

    def test_marks_recording_boundary(self) -> None:
        entries = build_entries([make_analysis("r1", ("前半",)), make_analysis("r2", ("後半",))])
        assert render_listing(entries).splitlines() == [
            "0\t0.0\t1.0\t前半",
            BOUNDARY_NOTE,
            "1\t0.0\t1.0\t後半",
        ]

    def test_text_cannot_break_the_table(self) -> None:
        chunk = entries_of("x")[0].chunk
        entry = JudgeEntry(number=0, chunk=chunk, text="a\tb\n9\t0.0\t1.0\tc")
        assert render_listing([entry]).splitlines() == ["0\t0.0\t1.0\ta b 9 0.0 1.0 c"]


class TestParseDecisions:
    def test_reads_delete_list(self) -> None:
        entries = entries_of("a", "b", "c")
        output = delete_output(
            {"id": 0, "kind": "retake", "reason": "直後に言い直し", "superseded_by": 2},
            {"id": 1, "kind": "misspeak", "reason": "途中で途切れた"},
        )
        assert parse_decisions(output, entries) == (
            Decision(0, CutKind.RETAKE, "直後に言い直し", 2),
            Decision(1, CutKind.MISSPEAK, "途中で途切れた", None),
        )

    def test_accepts_surrounding_text_and_code_fence(self) -> None:
        entries = entries_of("a")
        body = delete_output({"id": 0, "kind": "noise", "reason": "独り言"})
        output = f"判定しました。\n```json\n{body}\n```\n以上です。"
        assert numbers(parse_decisions(output, entries)) == [0]

    def test_empty_delete_list(self) -> None:
        assert parse_decisions('{"delete": []}', entries_of("a")) == ()

    def test_drops_ids_that_were_not_given(self) -> None:
        # 文字起こしの内容に誘導されても、渡していないチャンクは削除しない（Design Doc 3-5-1）
        entries = entries_of("a", "", "c")
        output = delete_output(
            {"id": 1, "kind": "noise", "reason": "空"},
            {"id": 99, "kind": "noise", "reason": "範囲外"},
            {"id": 2, "kind": "noise", "reason": "独り言"},
        )
        assert numbers(parse_decisions(output, entries)) == [2]

    def test_first_decision_wins_for_duplicate_ids(self) -> None:
        output = delete_output(
            {"id": 0, "kind": "noise", "reason": "一つ目"},
            {"id": 0, "kind": "misspeak", "reason": "二つ目"},
        )
        assert parse_decisions(output, entries_of("a")) == (
            Decision(0, CutKind.NOISE, "一つ目", None),
        )

    @pytest.mark.parametrize("superseded_by", [99, 0, "2", [1, 2], True, None])
    def test_unusable_superseded_by_is_ignored(self, superseded_by: object) -> None:
        output = delete_output(
            {"id": 0, "kind": "retake", "reason": "言い直し", "superseded_by": superseded_by}
        )
        assert parse_decisions(output, entries_of("a", "b")) == (
            Decision(0, CutKind.RETAKE, "言い直し", None),
        )

    def test_long_reason_is_truncated(self) -> None:
        output = delete_output({"id": 0, "kind": "noise", "reason": "あ" * 1000})
        (decision,) = parse_decisions(output, entries_of("a"))
        assert len(decision.reason) == MAX_REASON_CHARS

    @pytest.mark.parametrize(
        "output",
        [
            "",
            "判定できませんでした",
            "{not json}",
            "[1, 2]",
            '{"delete": "none"}',
            '{"remove": []}',
            '{"delete": [3]}',
            '{"delete": [{"kind": "noise", "reason": "x"}]}',
            '{"delete": [{"id": "0", "kind": "noise", "reason": "x"}]}',
            '{"delete": [{"id": true, "kind": "noise", "reason": "x"}]}',
            '{"delete": [{"id": 0, "kind": "silence", "reason": "x"}]}',
            '{"delete": [{"id": 0, "kind": "filler", "reason": "x"}]}',
            '{"delete": [{"id": 0, "kind": ["noise"], "reason": "x"}]}',
            '{"delete": [{"id": 0, "kind": "noise"}]}',
            '{"delete": [{"id": 0, "kind": "noise", "reason": "  "}]}',
            '{"delete": [{"id": 0, "kind": "noise", "reason": 5}]}',
        ],
    )
    def test_rejects_output_that_breaks_the_schema(self, output: str) -> None:
        with pytest.raises(JudgeOutputError):
            parse_decisions(output, entries_of("a"))


class TestSplitWindows:
    def test_single_window_up_to_the_limit(self) -> None:
        settings = JudgeSettings(max_chunks=10, overlap=4)
        assert split_windows(10, settings) == (Window(0, 10, 0, 10),)

    def test_overlapping_windows_own_adjacent_ranges(self) -> None:
        settings = JudgeSettings(max_chunks=10, overlap=4)
        assert split_windows(20, settings) == (
            Window(0, 10, 0, 8),
            Window(6, 16, 8, 14),
            Window(12, 20, 14, 20),
        )

    def test_no_window_for_a_tail_the_previous_one_already_covers(self) -> None:
        settings = JudgeSettings(max_chunks=10, overlap=4)
        assert split_windows(16, settings) == (Window(0, 10, 0, 8), Window(6, 16, 8, 16))

    def test_one_chunk_over_the_limit(self) -> None:
        settings = JudgeSettings(max_chunks=10, overlap=4)
        assert split_windows(11, settings) == (Window(0, 10, 0, 8), Window(6, 11, 8, 11))

    def test_nothing_to_judge(self) -> None:
        assert split_windows(0, JudgeSettings()) == ()

    @pytest.mark.parametrize(("max_chunks", "overlap"), [(1, 0), (10, 10), (10, -1), (0, 0)])
    def test_rejects_invalid_settings(self, max_chunks: int, overlap: int) -> None:
        with pytest.raises(ValueError):
            JudgeSettings(max_chunks=max_chunks, overlap=overlap)

    def test_default_threshold(self) -> None:
        assert JudgeSettings().max_chunks == 300


class TestJudgeEntries:
    def test_sends_prompt_and_listing_and_returns_decisions(self) -> None:
        entries = entries_of("a", "b")
        model = FakeModel([delete_output({"id": 0, "kind": "noise", "reason": "独り言"})])
        decisions = judge_entries(model, entries, JudgeSettings(), prompt="指示文\n")
        assert numbers(decisions) == [0]
        assert model.prompts == ["指示文\n" + render_listing(entries)]

    def test_uses_bundled_prompt_by_default(self) -> None:
        model = FakeModel(['{"delete": []}'])
        judge_entries(model, entries_of("a"), JudgeSettings())
        assert model.prompts[0].startswith(load_prompt())

    def test_retries_once_when_output_is_unreadable(self) -> None:
        model = FakeModel(
            ["読めない出力", delete_output({"id": 1, "kind": "noise", "reason": "x"})]
        )
        decisions = judge_entries(model, entries_of("a", "b"), JudgeSettings(), prompt="p")
        assert numbers(decisions) == [1]
        assert len(model.prompts) == 2
        assert model.prompts[0] == model.prompts[1]

    def test_fails_after_second_unreadable_output(self) -> None:
        model = FakeModel(["読めない", "また読めない", '{"delete": []}'])
        with pytest.raises(JudgeOutputError, match="2 回"):
            judge_entries(model, entries_of("a"), JudgeSettings(), prompt="p")
        assert len(model.prompts) == 2

    def test_does_not_call_model_without_chunks(self) -> None:
        model = FakeModel([])
        assert judge_entries(model, (), JudgeSettings(), prompt="p") == ()
        assert model.prompts == []

    def test_judges_each_window_and_keeps_only_owned_decisions(self) -> None:
        entries = entries_of(*(f"t{i}" for i in range(16)))
        # 窓 1 は 0〜9 を見て 0〜7 を担当、窓 2 は 6〜15 を見て 8〜15 を担当
        first = delete_output(
            {"id": 2, "kind": "noise", "reason": "担当内"},
            {"id": 9, "kind": "misspeak", "reason": "後ろの文脈が足りない"},
        )
        second = delete_output(
            {"id": 6, "kind": "misspeak", "reason": "前の文脈が足りない"},
            {"id": 8, "kind": "retake", "reason": "担当内", "superseded_by": 12},
        )
        model = FakeModel([first, second])
        progress: list[float] = []
        decisions = judge_entries(
            model,
            entries,
            JudgeSettings(max_chunks=10, overlap=4),
            prompt="p",
            on_progress=progress.append,
        )
        assert decisions == (
            Decision(2, CutKind.NOISE, "担当内", None),
            Decision(8, CutKind.RETAKE, "担当内", 12),
        )
        assert model.prompts == [
            "p" + render_listing(entries[:10]),
            "p" + render_listing(entries[6:]),
        ]
        assert progress == [0.5, 1.0]

    def test_window_only_accepts_ids_it_was_given(self) -> None:
        entries = entries_of(*(f"t{i}" for i in range(16)))
        model = FakeModel(
            [delete_output({"id": 12, "kind": "noise", "reason": "窓の外"}), '{"delete": []}']
        )
        settings = JudgeSettings(max_chunks=10, overlap=4)
        assert judge_entries(model, entries, settings, prompt="p") == ()


class TestToSuggestions:
    def test_builds_suggestions_on_chunk_spans(self) -> None:
        entries = build_entries([make_analysis("r1", ("a", "b")), make_analysis("r2", ("c",))])
        decisions = (
            Decision(1, CutKind.RETAKE, "次のファイルで言い直し", 2),
            Decision(0, CutKind.NOISE, "独り言", None),
        )
        assert to_suggestions(entries, decisions) == (
            CutSuggestion(
                id="r1-c0000-judged",
                recording_id="r1",
                span=Interval(0, 1_000),
                kind=CutKind.NOISE,
                reason="独り言",
            ),
            CutSuggestion(
                id="r1-c0001-judged",
                recording_id="r1",
                span=Interval(2_000, 3_000),
                kind=CutKind.RETAKE,
                reason="次のファイルで言い直し",
                superseded_by="r2-c0000",
            ),
        )

    def test_rejects_decision_for_unknown_chunk(self) -> None:
        with pytest.raises(ValueError):
            to_suggestions(entries_of("a"), (Decision(5, CutKind.NOISE, "x", None),))


class TestInputKey:
    def test_same_input_gives_same_key(self) -> None:
        entries = entries_of("a", "b")
        assert input_key("p", entries, JudgeSettings()) == input_key(
            "p", entries_of("a", "b"), JudgeSettings()
        )

    def test_key_changes_with_prompt_text_chunks_and_windows(self) -> None:
        entries = entries_of("a", "b")
        base = input_key("p", entries, JudgeSettings())
        assert input_key("q", entries, JudgeSettings()) != base
        assert input_key("p", entries_of("a", "c"), JudgeSettings()) != base
        assert input_key("p", entries_of("a", "b", rid="r9"), JudgeSettings()) != base
        assert input_key("p", entries, JudgeSettings(max_chunks=10, overlap=2)) != base


def test_delete_output_helper_is_json() -> None:
    assert json.loads(delete_output({"id": 1}))["delete"] == [{"id": 1}]
