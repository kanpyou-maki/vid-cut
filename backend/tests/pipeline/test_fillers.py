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
