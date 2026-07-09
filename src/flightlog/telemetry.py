"""Load and validate drone telemetry logs (CSV).

This module is the data-quality gate. It reads a CSV, checks the schema and the
value ranges, drops rows it cannot trust, and reports whether the log is good
enough to analyse. It has no plotting dependency so it can run in a light CI job.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from itertools import pairwise

REQUIRED_COLUMNS = ("time_s", "lat", "lon", "alt_m", "battery_v", "speed_ms")

# Plausible ranges for a small drone flight. Rows outside these are dropped.
RANGES: dict[str, tuple[float, float]] = {
    "lat": (-90.0, 90.0),
    "lon": (-180.0, 180.0),
    "alt_m": (-10.0, 1000.0),
    "battery_v": (6.0, 30.0),
    "speed_ms": (0.0, 100.0),
}

# If more than this share of rows is unusable, treat the whole log as bad.
MAX_DROP_RATIO = 0.2


@dataclass(frozen=True)
class Sample:
    """One validated telemetry point."""

    time_s: float
    lat: float
    lon: float
    alt_m: float
    battery_v: float
    speed_ms: float


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a telemetry file."""

    samples: list[Sample]
    total_rows: int
    dropped_rows: int
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _in_ranges(values: dict[str, float]) -> bool:
    return all(low <= values[key] <= high for key, (low, high) in RANGES.items())


def _time_strictly_increasing(samples: list[Sample]) -> bool:
    return all(b.time_s > a.time_s for a, b in pairwise(samples))


def validate_file(path: str) -> ValidationResult:
    """Validate a telemetry CSV and return the usable samples plus any errors."""
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        return ValidationResult(
            samples=[],
            total_rows=len(rows),
            dropped_rows=0,
            errors=[f"missing required columns: {', '.join(missing)}"],
        )

    samples: list[Sample] = []
    dropped = 0
    for row in rows:
        try:
            values = {c: float(row[c]) for c in REQUIRED_COLUMNS}
        except (TypeError, ValueError):
            dropped += 1
            continue
        if not _in_ranges(values):
            dropped += 1
            continue
        samples.append(Sample(**values))

    errors: list[str] = []
    if len(samples) < 2:
        errors.append("not enough valid rows to analyse a flight (need at least 2)")
    elif not _time_strictly_increasing(samples):
        errors.append("time_s is not strictly increasing")
    if rows and dropped / len(rows) > MAX_DROP_RATIO:
        errors.append(f"too many invalid rows: {dropped} of {len(rows)} dropped")

    return ValidationResult(
        samples=samples,
        total_rows=len(rows),
        dropped_rows=dropped,
        errors=errors,
    )
