import pytest

from vidcut.domain.intervals import Interval, merge, subtract


class TestInterval:
    def test_duration_is_end_minus_start(self) -> None:
        assert Interval(100, 350).duration_ms == 250

    @pytest.mark.parametrize(("start", "end"), [(-1, 10), (10, 10), (20, 10)])
    def test_rejects_negative_or_empty_span(self, start: int, end: int) -> None:
        with pytest.raises(ValueError):
            Interval(start, end)

    def test_contains_is_half_open(self) -> None:
        span = Interval(100, 200)
        assert span.contains(100)
        assert span.contains(199)
        assert not span.contains(200)
        assert not span.contains(99)

    def test_overlaps_excludes_touching_spans(self) -> None:
        assert Interval(0, 100).overlaps(Interval(50, 150))
        assert not Interval(0, 100).overlaps(Interval(100, 200))

    def test_is_immutable(self) -> None:
        span = Interval(0, 10)
        with pytest.raises(AttributeError):
            span.start_ms = 5  # type: ignore[misc]


class TestMerge:
    def test_returns_empty_for_no_input(self) -> None:
        assert merge([]) == ()

    def test_sorts_and_merges_overlapping_and_touching_spans(self) -> None:
        spans = [Interval(300, 400), Interval(0, 100), Interval(100, 150), Interval(120, 200)]
        assert merge(spans) == (Interval(0, 200), Interval(300, 400))

    def test_keeps_separated_spans(self) -> None:
        assert merge([Interval(0, 10), Interval(20, 30)]) == (Interval(0, 10), Interval(20, 30))

    def test_merges_spans_within_gap(self) -> None:
        assert merge([Interval(0, 10), Interval(15, 30)], gap_ms=5) == (Interval(0, 30),)

    def test_rejects_negative_gap(self) -> None:
        with pytest.raises(ValueError):
            merge([Interval(0, 10)], gap_ms=-1)


class TestSubtract:
    def test_returns_base_when_nothing_to_subtract(self) -> None:
        assert subtract(Interval(0, 1000), []) == (Interval(0, 1000),)

    def test_removes_cuts_inside_base(self) -> None:
        cuts = [Interval(100, 200), Interval(500, 600)]
        assert subtract(Interval(0, 1000), cuts) == (
            Interval(0, 100),
            Interval(200, 500),
            Interval(600, 1000),
        )

    def test_clips_cuts_extending_outside_base(self) -> None:
        cuts = [Interval(0, 150), Interval(900, 2000)]
        assert subtract(Interval(100, 1000), cuts) == (Interval(150, 900),)

    def test_returns_empty_when_base_is_fully_cut(self) -> None:
        assert subtract(Interval(100, 200), [Interval(0, 300)]) == ()

    def test_handles_unsorted_and_overlapping_cuts(self) -> None:
        cuts = [Interval(400, 500), Interval(100, 300), Interval(250, 350)]
        assert subtract(Interval(0, 600), cuts) == (
            Interval(0, 100),
            Interval(350, 400),
            Interval(500, 600),
        )


@pytest.mark.parametrize("bad", [1.5, True, "10"])
def test_interval_rejects_non_int_values(bad: object) -> None:
    with pytest.raises(TypeError):
        Interval(bad, 100)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Interval(0, bad)  # type: ignore[arg-type]
