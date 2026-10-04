import pytest

from vidcut.domain.intervals import Interval
from vidcut.domain.models import CutKind, SpeechChunk, Token
from vidcut.pipeline.fillers import detect_fillers


def chunk_with(
    text: str, *, start: int = 0, gaps: dict[int, int] | None = None
) -> tuple[SpeechChunk, tuple[Token, ...]]:
    """1 文字 100ms で並べる。gaps={i: ms} で i 文字目の前に間をあける。"""
    tokens: list[Token] = []
    cursor = start
    for i, ch in enumerate(text):
        cursor += (gaps or {}).get(i, 0)
        tokens.append(
            Token(
                id=f"t{i}",
                recording_id="r1",
                chunk_id="r1-c0000",
                text=ch,
                span=Interval(cursor, cursor + 100),
                asr_confidence=0.9,
                align_score=0.9,
            )
        )
        cursor += 100
    chunk = SpeechChunk(id="r1-c0000", recording_id="r1", span=Interval(start, cursor))
    return chunk, tuple(tokens)


def spans(text: str, gaps: dict[int, int] | None = None) -> list[tuple[Interval, str]]:
    chunk, tokens = chunk_with(text, gaps=gaps)
    return [(s.span, s.reason) for s in detect_fillers([chunk], tokens)]


def tokens_at(*items: tuple[str, int, int]) -> tuple[Token, ...]:
    """(文字, 開始, 終了) を、そのままの時刻でトークンにする。"""
    return tuple(
        Token(
            id=f"t{i}",
            recording_id="r1",
            chunk_id="r1-c0000",
            text=text,
            span=Interval(start, end),
            asr_confidence=0.9,
            align_score=0.9,
        )
        for i, (text, start, end) in enumerate(items)
    )


def chunk_at(start: int, end: int) -> SpeechChunk:
    return SpeechChunk(id="r1-c0000", recording_id="r1", span=Interval(start, end))


class TestDetectFillers:
    def test_chunk_consisting_of_filler_is_a_candidate(self) -> None:
        assert spans("えーと") == [(Interval(0, 300), "フィラー「えーと」")]

    def test_filler_separated_by_pauses_is_a_candidate(self) -> None:
        # 「えー」の後に 200ms の間があり、そこから本題に入る。次の語の 50ms 手前まで削る
        assert spans("えーそれでは", gaps={2: 200}) == [(Interval(0, 350), "フィラー「えー」")]

    def test_filler_inside_a_word_without_pause_is_kept(self) -> None:
        assert spans("えーそれでは") == []

    def test_punctuation_is_ignored_when_measuring_pauses(self) -> None:
        # 前の語「は」の終わり（200）の 50ms あとから、次の語「次」の頭（1000）の 50ms 手前まで
        assert spans("では、あのー、次に", gaps={3: 150, 6: 150}) == [
            (Interval(250, 950), "フィラー「あのー」")
        ]

    def test_punctuation_next_to_the_filler_counts_as_a_break(self) -> None:
        # 間がなくても、読点で区切られていれば候補にする
        assert spans("では、あのー、次に") == [(Interval(250, 650), "フィラー「あのー」")]

    def test_punctuation_on_one_side_only_is_not_enough(self) -> None:
        assert spans("では、あのー次に") == []
        assert spans("ではあのー、次に") == []

    def test_long_vowels_of_any_length(self) -> None:
        assert spans("うーーん")[0][1] == "フィラー「うーーん」"

    def test_ambiguous_word_only_when_it_is_the_whole_chunk(self) -> None:
        assert spans("まあ") == [(Interval(0, 200), "フィラー「まあ」")]
        assert spans("まあいいでしょう", gaps={2: 300}) == []
        assert spans("まあ、いいでしょう") == []
        # チャンクの終わりまで削る（後ろの読点のぶんも）
        assert spans("その、") == [(Interval(0, 300), "フィラー「その」")]

    def test_suggestion_metadata(self) -> None:
        chunk, tokens = chunk_with("えっと")
        (suggestion,) = detect_fillers([chunk], tokens)
        assert suggestion.kind is CutKind.FILLER
        assert suggestion.recording_id == "r1"
        assert suggestion.id == "r1-c0000-filler-0"

    def test_no_tokens_no_fillers(self) -> None:
        chunk = SpeechChunk(id="r1-c0000", recording_id="r1", span=Interval(0, 1_000))
        assert detect_fillers([chunk], []) == ()


class TestCutSpan:
    """削除する区間は、位置合わせの時刻ではなく、前後の語で決める（Design Doc 3-2）。"""

    def test_covers_a_drawn_out_filler_that_the_aligner_squeezed(self) -> None:
        # 実素材の形: 「えー」に 41ms しか付かないが、声は次の語の直前まで続いている
        tokens = tokens_at(
            ("え", 220, 240), ("ー", 240, 261), ("、", 261, 281), ("見", 600, 700), ("て", 700, 800)
        )
        (suggestion,) = detect_fillers([chunk_at(200, 800)], tokens)
        assert suggestion.span == Interval(200, 550)

    def test_starts_at_the_chunk_head_and_ends_at_the_chunk_end(self) -> None:
        tokens = tokens_at(("え", 300, 320), ("ー", 320, 340), ("と", 340, 360))
        (suggestion,) = detect_fillers([chunk_at(100, 900)], tokens)
        assert suggestion.span == Interval(100, 900)

    def test_filler_at_the_end_of_a_chunk(self) -> None:
        assert spans("それでは、えー") == [(Interval(450, 700), "フィラー「えー」")]

    def test_is_never_narrower_than_the_aligned_filler(self) -> None:
        # 前後の語がすぐ隣にあるときは、位置合わせの時刻のまま
        tokens = tokens_at(
            ("は", 0, 100), ("、", 100, 120), ("え", 120, 220), ("ー", 220, 320),
            ("、", 320, 340), ("次", 340, 440),
        )  # fmt: skip
        (suggestion,) = detect_fillers([chunk_at(0, 440)], tokens)
        assert suggestion.span == Interval(120, 320)

    def test_does_not_stretch_far_beyond_the_aligned_filler(self) -> None:
        # 文字のない長い区間には、書き起こされなかった発話があるかもしれない。広げるのは 1 秒まで
        tokens = tokens_at(("え", 3_000, 3_020), ("ー", 3_020, 3_040), ("と", 3_040, 3_060))
        (suggestion,) = detect_fillers([chunk_at(0, 9_000)], tokens)
        assert suggestion.span == Interval(2_000, 4_060)

    def test_stretch_limit_is_configurable(self) -> None:
        tokens = tokens_at(("え", 3_000, 3_020), ("ー", 3_020, 3_040), ("と", 3_040, 3_060))
        (suggestion,) = detect_fillers([chunk_at(0, 9_000)], tokens, max_stretch_ms=200)
        assert suggestion.span == Interval(2_800, 3_260)

    def test_guard_is_configurable(self) -> None:
        chunk, tokens = chunk_with("えーそれでは", gaps={2: 200})
        (suggestion,) = detect_fillers([chunk], tokens, guard_ms=0)
        assert suggestion.span == Interval(0, 400)

    def test_rejects_a_negative_guard(self) -> None:
        chunk, tokens = chunk_with("えーと")
        with pytest.raises(ValueError, match="guard_ms"):
            detect_fillers([chunk], tokens, guard_ms=-1)

    def test_rejects_a_negative_stretch_limit(self) -> None:
        chunk, tokens = chunk_with("えーと")
        with pytest.raises(ValueError, match="max_stretch_ms"):
            detect_fillers([chunk], tokens, max_stretch_ms=-1)


class TestMultiCharacterTokens:
    """トークンは 1 文字が基本だが、複数の文字を持つこともある（文字とトークンの位置がずれる）。"""

    def test_filler_after_a_multi_character_token(self) -> None:
        tokens = tokens_at(("API", 0, 300), ("は", 300, 400), ("、", 400, 420), ("えー", 420, 600))
        (suggestion,) = detect_fillers([chunk_at(0, 900)], tokens)
        assert (suggestion.span, suggestion.reason) == (Interval(420, 900), "フィラー「えー」")

    def test_filler_that_is_only_part_of_a_token_is_not_a_candidate(self) -> None:
        # 「えーと」が、ほかの文字と同じトークンに入っている。トークンの途中では切れない
        tokens = tokens_at(("えーとそれ", 0, 500), ("では", 700, 900))
        assert detect_fillers([chunk_at(0, 900)], tokens) == ()


class TestFillerRuns:
    """続いたフィラーは、まとめて 1 つの候補にする。"""

    def test_fillers_separated_by_punctuation_become_one(self) -> None:
        assert spans("次は、あー、えーと") == [(Interval(250, 900), "フィラー「あー、えーと」")]

    def test_fillers_without_punctuation_become_one(self) -> None:
        assert spans("あーあー") == [(Interval(0, 400), "フィラー「あーあー」")]

    def test_ambiguous_word_goes_with_the_filler_next_to_it(self) -> None:
        # 実素材の形: 「まあ、あのー、実際に」
        assert spans("まあ、あのー、実際に") == [(Interval(0, 650), "フィラー「まあ、あのー」")]
        assert spans("えー、まあ、次に") == [(Interval(0, 550), "フィラー「えー、まあ」")]

    def test_ambiguous_word_that_runs_into_the_next_word_stays(self) -> None:
        # 「その方法」の「その」は内容語。手前のフィラーだけを消す
        assert spans("えー、その方法は") == [(Interval(0, 250), "フィラー「えー」")]

    def test_run_of_ambiguous_words_is_cut_only_as_a_whole_chunk(self) -> None:
        assert spans("まあ、その") == [(Interval(0, 500), "フィラー「まあ、その」")]
        assert spans("まあ、その、次に") == []

    def test_separate_fillers_in_a_chunk_are_numbered(self) -> None:
        chunk, tokens = chunk_with("えー、次に、あのー、最後に")
        found = detect_fillers([chunk], tokens)
        assert [(s.id, s.reason) for s in found] == [
            ("r1-c0000-filler-0", "フィラー「えー」"),
            ("r1-c0000-filler-1", "フィラー「あのー」"),
        ]

    def test_filler_that_runs_into_the_next_word_does_not_break_a_run(self) -> None:
        # 2 つ目の「えー」は語につながっている。区切れている 1 つ目だけを消す
        assert spans("えー、えーそれでは") == [(Interval(0, 250), "フィラー「えー」")]


class TestFillerAtTheChunkEnd:
    """チャンクの終わり（後ろは無音）のフィラーは、前が区切れていなくても候補にする。

    位置合わせは、フィラーの前の間を詰めてしまうことがある（実素材の「次の三にはあー」）。
    """

    def test_filler_that_ends_the_chunk_is_a_candidate(self) -> None:
        assert spans("次はあー") == [(Interval(200, 400), "フィラー「あー」")]

    def test_run_that_ends_the_chunk_is_a_candidate(self) -> None:
        assert spans("次はあーえーと") == [(Interval(200, 700), "フィラー「あーえーと」")]

    def test_ambiguous_word_that_ends_the_chunk_stays(self) -> None:
        assert spans("次はその") == []
        assert spans("次はまあその") == []

    def test_filler_at_the_chunk_head_still_needs_a_break_after_it(self) -> None:
        # 語の頭かもしれない（後ろが無音ではない）
        assert spans("えーそれでは") == []

    def test_filler_in_the_middle_still_needs_breaks(self) -> None:
        assert spans("次はあーそれでは") == []


class TestWordsThatOnlyLookLikeFillers:
    """辞書に一致しても、語の一部や内容語は消さない（誤削除を、削除漏れより重く見る）。"""

    @pytest.mark.parametrize(
        "text",
        [
            "ええ",
            "そのまま",
            "あのね",
            "その方法は",
            "うーんと",  # 「うーん」に「と」が続いている
            "えーえーそれでは",  # まとまりの外側が区切れていない
            "まあその話は",
        ],
    )
    def test_is_not_a_candidate(self, text: str) -> None:
        assert spans(text) == []

    def test_ambiguous_word_before_a_chunk_final_filler_stays(self) -> None:
        # 「まあ」は残し、チャンクの終わりのフィラーだけを消す
        assert spans("次はまああー") == [(Interval(400, 600), "フィラー「あー」")]
        assert spans("次はまあ、えー") == [(Interval(450, 700), "フィラー「えー」")]


class TestBoundaries:
    def test_gap_of_exactly_the_minimum_is_a_break(self) -> None:
        assert spans("えーそれでは", gaps={2: 99}) == []
        assert spans("えーそれでは", gaps={2: 100}) == [(Interval(0, 250), "フィラー「えー」")]

    @pytest.mark.parametrize(
        ("filler_start", "cut_start"),
        [(149, 149), (150, 150), (151, 150), (400, 150)],
    )
    def test_guard_after_the_previous_word(self, filler_start: int, cut_start: int) -> None:
        # 前の語の終わり（100）の 50ms あとから。フィラーの頭がそれより手前なら、フィラーの頭から
        end = filler_start + 200
        tokens = tokens_at(
            ("は", 0, 100),
            ("、", 100, 110),
            ("え", filler_start, filler_start + 100),
            ("ー", filler_start + 100, end),
        )
        (suggestion,) = detect_fillers([chunk_at(0, end)], tokens)
        assert suggestion.span == Interval(cut_start, end)

    @pytest.mark.parametrize(
        ("next_start", "cut_end"),
        [(349, 300), (350, 300), (351, 301), (900, 850)],
    )
    def test_guard_before_the_next_word(self, next_start: int, cut_end: int) -> None:
        # 次の語の頭の 50ms 手前まで。フィラーの終わり（300）がそれより後ろなら、そこまで
        tokens = tokens_at(
            ("え", 100, 200),
            ("ー", 200, 300),
            ("、", 300, 310),
            ("次", next_start, next_start + 100),
        )
        (suggestion,) = detect_fillers([chunk_at(100, next_start + 100)], tokens)
        assert suggestion.span == Interval(100, cut_end)

    @pytest.mark.parametrize(
        ("chunk", "expected"),
        [
            ((2_000, 4_060), Interval(2_000, 4_060)),  # ちょうど 1 秒ずつ
            ((1_999, 4_061), Interval(2_000, 4_060)),  # 1 秒を超えるぶんは広げない
            ((2_500, 9_000), Interval(2_500, 4_060)),  # 後ろだけ上限にかかる
            ((0, 3_500), Interval(2_000, 3_500)),  # 前だけ上限にかかる
        ],
    )
    def test_stretch_limit_on_each_side(self, chunk: tuple[int, int], expected: Interval) -> None:
        tokens = tokens_at(("え", 3_000, 3_020), ("ー", 3_020, 3_040), ("と", 3_040, 3_060))
        (suggestion,) = detect_fillers([chunk_at(*chunk)], tokens)
        assert suggestion.span == expected

    def test_tokens_that_stick_out_of_the_chunk_are_covered(self) -> None:
        # 位置合わせの時刻が、チャンクの範囲から少しはみ出すことがある
        early = tokens_at(("え", 250, 350), ("ー", 350, 450), ("と", 450, 550))
        late = tokens_at(("え", 600, 700), ("ー", 700, 800), ("と", 800, 950))
        assert detect_fillers([chunk_at(300, 900)], early)[0].span == Interval(250, 900)
        assert detect_fillers([chunk_at(300, 900)], late)[0].span == Interval(300, 950)


class TestRealRecordings:
    """受け入れチェック（forTest01〜03）で見つかった形。時刻は、実際の位置合わせの結果。"""

    def test_filler_squeezed_to_41ms(self) -> None:
        # forTest02 1:20「えー、ぜひやってみ…」。声は次の語の直前まで続いていた
        tokens = tokens_at(
            ("え", 79_534, 79_554), ("ー", 79_554, 79_575), ("、", 79_575, 79_595),
            ("ぜ", 79_796, 79_900), ("ひ", 79_900, 80_000),
        )  # fmt: skip
        (suggestion,) = detect_fillers([chunk_at(79_514, 81_370)], tokens)
        assert suggestion.span == Interval(79_514, 79_746)

    def test_filler_that_ends_a_chunk_without_a_gap_before_it(self) -> None:
        # forTest03 1:20「次の三にはあー」。読点も間もないが、後ろは無音
        tokens = tokens_at(
            ("次", 79_599, 79_881), ("の", 79_881, 80_423), ("三", 80_423, 80_865),
            ("に", 80_865, 81_026), ("は", 81_026, 81_528), ("あ", 81_528, 81_688),
            ("ー", 81_688, 81_708),
        )  # fmt: skip
        (suggestion,) = detect_fillers([chunk_at(79_519, 82_291)], tokens)
        assert (suggestion.span, suggestion.reason) == (
            Interval(81_528, 82_291),
            "フィラー「あー」",
        )
