import pytest

from numstats.core import Summary, parse_numbers, summarize


def test_parse_numbers_handles_spaces_and_commas():
    assert parse_numbers("1, 2  3,4") == [1.0, 2.0, 3.0, 4.0]


def test_parse_numbers_rejects_garbage():
    with pytest.raises(ValueError):
        parse_numbers("1 2 banana")


def test_summarize_basic():
    s = summarize([1, 2, 3, 4])
    assert isinstance(s, Summary)
    assert s.count == 4
    assert s.minimum == 1
    assert s.maximum == 4
    assert s.mean == pytest.approx(2.5)
    assert s.median == pytest.approx(2.5)


def test_summarize_known_stdev():
    # The population standard deviation of this classic dataset is exactly 2.0 --
    # a "golden" sanity check, the same idea as checking the ISS orbital period
    # in the bigger telemetry project.
    s = summarize([2, 4, 4, 4, 5, 5, 7, 9])
    assert s.stdev == pytest.approx(2.0)


def test_summarize_empty_raises():
    with pytest.raises(ValueError):
        summarize([])
