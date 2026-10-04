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


class TestDetectFillers:
    def test_chunk_consisting_of_filler_is_a_candidate(self) -> None:
        assert spans("えーと") == [(Interval(0, 300), "フィラー「えーと」")]

    def test_filler_separated_by_pauses_is_a_candidate(self) -> None:
        # 「えー」の後に 200ms の間があり、そこから本題に入る
        assert spans("えーそれでは", gaps={2: 200}) == [(Interval(0, 200), "フィラー「えー」")]

    def test_filler_inside_a_word_without_pause_is_kept(self) -> None:
        assert spans("えーそれでは") == []

    def test_punctuation_is_ignored_when_measuring_pauses(self) -> None:
        assert spans("では、あのー、次に", gaps={3: 150, 6: 150}) == [
            (Interval(450, 750), "フィラー「あのー」")
        ]

    def test_long_vowels_of_any_length(self) -> None:
        assert spans("うーーん")[0][1] == "フィラー「うーーん」"

    def test_ambiguous_word_only_when_it_is_the_whole_chunk(self) -> None:
        assert spans("まあ") == [(Interval(0, 200), "フィラー「まあ」")]
        assert spans("まあいいでしょう", gaps={2: 300}) == []
        assert spans("その、") == [(Interval(0, 200), "フィラー「その」")]

    def test_suggestion_metadata(self) -> None:
        chunk, tokens = chunk_with("えっと")
        (suggestion,) = detect_fillers([chunk], tokens)
        assert suggestion.kind is CutKind.FILLER
        assert suggestion.recording_id == "r1"
        assert suggestion.id == "r1-c0000-filler-0"

    def test_no_tokens_no_fillers(self) -> None:
        chunk = SpeechChunk(id="r1-c0000", recording_id="r1", span=Interval(0, 1_000))
        assert detect_fillers([chunk], []) == ()


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


class TestCutSpan:
    """削る区間は、フィラーの文字の時刻だけ。前後の語やチャンクの端のほうへは広げない。

    位置合わせは、次の語の頭を実際より遅く置くことがある。広げると、その語の頭を削る
    （実素材では「うーん」の次の「セ」が半分切れた。ユーザー決定 46）。
    """

    def test_cut_does_not_reach_toward_the_neighbouring_words(self) -> None:
        tokens = tokens_at(
            ("は", 0, 100),
            ("う", 400, 600),
            ("ー", 600, 800),
            ("ん", 800, 1_000),
            ("セ", 1_200, 1_300),
        )
        (suggestion,) = detect_fillers([chunk_at(0, 1_300)], tokens)
        assert suggestion.span == Interval(400, 1_000)

    def test_cut_does_not_reach_the_chunk_edges(self) -> None:
        tokens = tokens_at(("え", 200, 300), ("ー", 300, 400))
        (suggestion,) = detect_fillers([chunk_at(0, 2_000)], tokens)
        assert suggestion.span == Interval(200, 400)

    def test_token_times_out_of_order_still_give_a_valid_span(self) -> None:
        # 位置合わせの時刻は、文字の順と前後することがある
        tokens = tokens_at(("え", 500, 600), ("ー", 450, 480))
        (suggestion,) = detect_fillers([chunk_at(0, 1_000)], tokens)
        assert suggestion.span == Interval(450, 600)


class TestDrawnOutEndings:
    """語尾の伸ばし（「そうですよねえー」）は、フィラーにしない（ユーザー決定 46）。"""

    def test_ending_that_runs_on_from_the_word_is_kept(self) -> None:
        assert spans("そうですよねえー") == []

    def test_punctuation_alone_does_not_separate_a_filler(self) -> None:
        # 文字起こしが「、」を挟んでも、声が続いていれば（間がなければ）語尾の伸ばしとして残す
        tokens = tokens_at(
            ("よ", 0, 100), ("ね", 100, 200), ("、", 200, 220), ("え", 220, 320), ("ー", 320, 420)
        )
        assert detect_fillers([chunk_at(0, 420)], tokens) == ()


class TestMultiCharacterTokens:
    """トークンは 1 文字が基本だが、複数の文字を持つこともある（文字とトークンの位置がずれる）。"""

    def test_filler_after_a_multi_character_token(self) -> None:
        tokens = tokens_at(("API", 0, 300), ("は", 300, 400), ("、", 400, 420), ("えー", 600, 800))
        (suggestion,) = detect_fillers([chunk_at(0, 900)], tokens)
        assert (suggestion.span, suggestion.reason) == (Interval(600, 800), "フィラー「えー」")

    def test_filler_that_is_only_part_of_a_token_is_not_a_candidate(self) -> None:
        # 「えーと」が、ほかの文字と同じトークンに入っている。トークンの途中では切れない
        tokens = tokens_at(("えーとそれ", 0, 500), ("では", 700, 900))
        assert detect_fillers([chunk_at(0, 900)], tokens) == ()
