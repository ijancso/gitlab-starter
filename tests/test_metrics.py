import pytest

from flightlog.metrics import FlightMetrics, compute_metrics, haversine_m
from flightlog.telemetry import Sample


def test_haversine_golden():
    # One degree of latitude is about 111.19 km with R = 6,371,000 m.
    # This is the "known answer" sanity check, like checking a known orbital
    # period in the bigger telemetry project.
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_195, rel=0.001)


def test_haversine_zero_distance():
    assert haversine_m(10.0, 20.0, 10.0, 20.0) == pytest.approx(0.0)


def _sample(t, lat, lon, alt, batt, spd):
    return Sample(time_s=t, lat=lat, lon=lon, alt_m=alt, battery_v=batt, speed_ms=spd)


def test_compute_metrics_basic():
    samples = [
        _sample(0, -43.5321, 172.6362, 0, 16.8, 0),
        _sample(10, -43.5321, 172.6372, 50, 16.0, 8),
        _sample(20, -43.5321, 172.6382, 30, 15.4, 5),
    ]
    m = compute_metrics(samples)
    assert isinstance(m, FlightMetrics)
    assert m.duration_s == 20
    assert m.max_altitude_m == 50
    assert m.min_battery_v == 15.4
    assert m.max_speed_ms == 8
    assert m.sample_count == 3
    assert m.distance_m > 0


def test_compute_metrics_needs_two_samples():
    with pytest.raises(ValueError):
        compute_metrics([_sample(0, 0, 0, 0, 16, 0)])
