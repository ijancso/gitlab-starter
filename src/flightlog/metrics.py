"""Compute derived flight metrics from validated telemetry samples.

Pure, dependency-free functions -- easy to unit test and to sanity-check with
known values (see the haversine golden test).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from itertools import pairwise

from flightlog.telemetry import Sample

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class FlightMetrics:
    """Summary metrics for one flight."""

    duration_s: float
    distance_m: float
    max_altitude_m: float
    min_battery_v: float
    max_speed_ms: float
    sample_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def compute_metrics(samples: list[Sample]) -> FlightMetrics:
    """Compute flight metrics from at least two validated samples."""
    if len(samples) < 2:
        raise ValueError("need at least 2 samples to compute flight metrics")

    distance = 0.0
    for a, b in pairwise(samples):
        distance += haversine_m(a.lat, a.lon, b.lat, b.lon)

    return FlightMetrics(
        duration_s=samples[-1].time_s - samples[0].time_s,
        distance_m=distance,
        max_altitude_m=max(s.alt_m for s in samples),
        min_battery_v=min(s.battery_v for s in samples),
        max_speed_ms=max(s.speed_ms for s in samples),
        sample_count=len(samples),
    )
