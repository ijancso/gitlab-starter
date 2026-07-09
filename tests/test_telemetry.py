import textwrap

from flightlog.telemetry import validate_file

GOOD = """\
time_s,lat,lon,alt_m,battery_v,speed_ms
0,-43.5321,172.6362,0,16.8,0
1,-43.5321,172.6363,10,16.7,3
2,-43.5320,172.6364,20,16.6,4
"""


def _write(tmp_path, text):
    path = tmp_path / "log.csv"
    path.write_text(textwrap.dedent(text))
    return str(path)


def test_good_log_passes(tmp_path):
    result = validate_file(_write(tmp_path, GOOD))
    assert result.ok
    assert len(result.samples) == 3
    assert result.dropped_rows == 0


def test_missing_column_fails(tmp_path):
    bad = "time_s,lat,lon,alt_m,battery_v\n0,-43.5,172.6,0,16.8\n"
    result = validate_file(_write(tmp_path, bad))
    assert not result.ok
    assert any("missing required columns" in e for e in result.errors)


def test_non_monotonic_time_fails(tmp_path):
    bad = """\
    time_s,lat,lon,alt_m,battery_v,speed_ms
    0,-43.5321,172.6362,0,16.8,0
    0,-43.5321,172.6363,10,16.7,3
    """
    result = validate_file(_write(tmp_path, bad))
    assert not result.ok
    assert any("increasing" in e for e in result.errors)


def test_out_of_range_row_is_dropped(tmp_path):
    # One row has an impossible latitude and should be dropped (1 of 3 = 33%),
    # which also trips the "too many invalid rows" guard.
    bad = """\
    time_s,lat,lon,alt_m,battery_v,speed_ms
    0,-43.5321,172.6362,0,16.8,0
    1,999,172.6363,10,16.7,3
    2,-43.5320,172.6364,20,16.6,4
    """
    result = validate_file(_write(tmp_path, bad))
    assert result.dropped_rows == 1
