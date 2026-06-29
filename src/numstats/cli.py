"""Command-line interface for numstats."""

from __future__ import annotations

import argparse
import sys

from numstats.core import parse_numbers, summarize


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code (0 = success)."""
    parser = argparse.ArgumentParser(
        prog="numstats",
        description="Compute summary statistics from a list of numbers.",
    )
    parser.add_argument(
        "numbers",
        nargs="*",
        help="numbers to summarize; if omitted, numbers are read from stdin",
    )
    args = parser.parse_args(argv)

    raw = " ".join(args.numbers) if args.numbers else sys.stdin.read()

    try:
        numbers = parse_numbers(raw)
        summary = summarize(numbers)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"count  {summary.count}")
    print(f"min    {summary.minimum:g}")
    print(f"max    {summary.maximum:g}")
    print(f"mean   {summary.mean:g}")
    print(f"median {summary.median:g}")
    print(f"stdev  {summary.stdev:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
