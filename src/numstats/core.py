"""Pure functions for computing summary statistics.

These functions are dependency-free and side-effect-free, which makes them
trivial to unit test. This is the part you later replace with real domain
logic when you grow the project.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class Summary:
    """Summary statistics for a list of numbers."""

    count: int
    minimum: float
    maximum: float
    mean: float
    median: float
    stdev: float


def parse_numbers(raw: str) -> list[float]:
    """Parse whitespace- or comma-separated numbers from a string.

    Raises ``ValueError`` if any token is not a valid number.
    """
    tokens = raw.replace(",", " ").split()
    return [float(token) for token in tokens]


def summarize(numbers: list[float]) -> Summary:
    """Compute summary statistics for a non-empty list of numbers.

    Raises ``ValueError`` if the list is empty.
    """
    if not numbers:
        raise ValueError("cannot summarize an empty list of numbers")
    return Summary(
        count=len(numbers),
        minimum=min(numbers),
        maximum=max(numbers),
        mean=statistics.fmean(numbers),
        median=statistics.median(numbers),
        stdev=statistics.pstdev(numbers),
    )
